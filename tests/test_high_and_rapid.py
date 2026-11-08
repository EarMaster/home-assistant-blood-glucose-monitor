"""Scenario tests for the high and rapid change alarms (synthetic data)."""

from __future__ import annotations

from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
import pytest

from custom_components.blood_glucose_monitor.const import CONF_TREND_ENTITY

from .conftest import GLUCOSE_ENTITY, READING_TIME_ENTITY, TREND_ENTITY
from .test_alarms import PAUSE_SWITCH, STATUS_SENSOR, Scenario, alarm, options

HIGH_THRESHOLD = "input_number.high_threshold"
URGENT_HIGH_THRESHOLD = "input_number.urgent_high_threshold"
RATE_ENTITY = "input_number.rate_limit"
HIGH_SENSOR = "sensor.alex_high_alarm"
RAPID_FALL_SENSOR = "sensor.alex_falling_fast_alarm"
RAPID_RISE_SENSOR = "sensor.alex_rising_fast_alarm"


def high_options(**overrides: Any) -> dict[str, Any]:
    """Return options with high, urgent high and both rapid alarms."""
    return options(
        **{
            CONF_TREND_ENTITY: TREND_ENTITY,
            "high": alarm(
                threshold_entity=HIGH_THRESHOLD,
                clear_offset=10,
                delay=30,
                repeat=30,
                snooze=120,
            ),
            "urgent_high": alarm(
                threshold_entity=URGENT_HIGH_THRESHOLD,
                clear_offset=10,
                delay=15,
                repeat=15,
                snooze=60,
            ),
            "rapid_fall": alarm(
                detection="trend", trend_level="quickly", delay=0, repeat=0, snooze=30
            ),
            "rapid_rise": alarm(
                detection="rate", rate_limit=3, delay=0, repeat=0, snooze=30
            ),
            **overrides,
        }
    )


@pytest.fixture
async def scenario(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> Scenario:
    """Return a scenario with high thresholds and a first normal reading."""
    hass.states.async_set(HIGH_THRESHOLD, "180", {"unit_of_measurement": "mg/dL"})
    hass.states.async_set(
        URGENT_HIGH_THRESHOLD, "250", {"unit_of_measurement": "mg/dL"}
    )
    hass.states.async_set(TREND_ENTITY, "steady")
    scenario = Scenario(hass, freezer)
    await scenario.reading(110)
    return scenario


async def test_high_alarm(scenario: Scenario) -> None:
    """High: above the threshold for the delay; ends at threshold minus offset."""
    await scenario.setup(high_options())
    await scenario.reading(190)
    await scenario.wait(25, 190)
    assert scenario.phases() == []
    await scenario.wait(5, 190)
    assert scenario.phases() == [("high", "triggered")]
    assert scenario.actions[0].data["title"] == "Alex: high glucose"
    assert scenario.state(STATUS_SENSOR) == "high"

    await scenario.reading(175)
    assert scenario.state(HIGH_SENSOR) == "active"
    await scenario.reading(170)
    assert scenario.phases(scenario.ends) == [("high", "resolved")]


async def test_urgent_high_has_priority(scenario: Scenario) -> None:
    """Urgent high starts after its own delay and wins the status over high."""
    await scenario.setup(high_options())
    await scenario.reading(260)
    await scenario.wait(15, 260)
    assert ("urgent_high", "triggered") in scenario.phases()
    await scenario.wait(15, 260)
    assert ("high", "triggered") in scenario.phases()
    assert scenario.state(STATUS_SENSOR) == "urgent_high"


async def test_high_is_paused(scenario: Scenario) -> None:
    """The pause applies to the high alarms."""
    await scenario.setup(high_options())
    await scenario.hass.services.async_call(
        "switch", "turn_on", {"entity_id": PAUSE_SWITCH}, blocking=True
    )
    await scenario.reading(260)
    await scenario.wait(30, 260)
    assert scenario.phases() == []


@pytest.mark.parametrize(
    ("level", "trend", "alarm_expected"),
    [
        ("quickly", "falling_quickly", True),
        ("quickly", "falling_very_quickly", True),
        ("quickly", "falling", False),
        ("very_quickly", "falling_quickly", False),
        ("very_quickly", "DoubleDown", False),
        ("very_quickly", "TripleDown", True),
    ],
)
async def test_rapid_fall_by_trend(
    scenario: Scenario, level: str, trend: str, alarm_expected: bool
) -> None:
    """Rapid fall by trend, from the selected trend level."""
    await scenario.setup(
        high_options(rapid_fall=alarm(detection="trend", trend_level=level, snooze=30))
    )
    scenario.hass.states.async_set(TREND_ENTITY, trend)
    await scenario.reading(100)
    assert (("rapid_fall", "triggered") in scenario.phases()) is alarm_expected
    if alarm_expected:
        assert scenario.state(STATUS_SENSOR) == "rapid_fall"
        assert scenario.actions[0].data["title"] == "Alex: glucose falling fast"
        scenario.hass.states.async_set(TREND_ENTITY, "steady")
        await scenario.reading(98)
        assert ("rapid_fall", "resolved") in scenario.phases(scenario.ends)


async def test_rapid_rise_by_rate(scenario: Scenario) -> None:
    """Rapid rise by the own rate between the last two readings."""
    await scenario.setup(high_options())
    await scenario.wait(5, 120)  # +2 mg/dL/min
    assert scenario.phases() == []
    await scenario.wait(5, 140)  # +4 mg/dL/min
    assert scenario.phases() == [("rapid_rise", "triggered")]
    assert scenario.actions[0].data["rate"] == 4.0
    await scenario.wait(5, 145)  # +1 mg/dL/min
    assert scenario.phases(scenario.ends) == [("rapid_rise", "resolved")]


async def test_rate_needs_close_readings(scenario: Scenario) -> None:
    """Readings more than 15 minutes apart give no rate."""
    await scenario.setup(high_options())
    await scenario.wait(20)
    await scenario.reading(200)
    assert ("rapid_rise", "triggered") not in scenario.phases()
    assert scenario.hass.states.get(STATUS_SENSOR).attributes["rate"] is None


async def test_rate_limit_entity(scenario: Scenario) -> None:
    """A rate limit entity with a rate unit takes precedence over the number."""
    hass = scenario.hass
    hass.states.async_set(RATE_ENTITY, "5", {"unit_of_measurement": "mg/dL/min"})
    await scenario.setup(
        high_options(
            rapid_rise=alarm(
                detection="rate", rate_limit=3, rate_entity=RATE_ENTITY, snooze=30
            )
        )
    )
    await scenario.wait(5, 130)  # +4 mg/dL/min, below 5
    assert scenario.phases() == []
    hass.states.async_set(RATE_ENTITY, "0.2", {"unit_of_measurement": "mmol/L/min"})
    await hass.async_block_till_done()  # 0.2 mmol/L/min = 3.6 mg/dL/min
    assert scenario.phases() == [("rapid_rise", "triggered")]

    hass.states.async_set(RATE_ENTITY, "2", {"unit_of_measurement": "%"})
    await scenario.wait(5, 160)  # unknown unit: nothing is guessed
    assert scenario.state(RAPID_RISE_SENSOR) == "active"


async def test_value_after_reading_time(scenario: Scenario) -> None:
    """A value arriving right after its reading time still counts for the rate."""
    hass = scenario.hass
    await scenario.setup(high_options())
    scenario.freezer.tick(300)
    hass.states.async_set(READING_TIME_ENTITY, dt_util.utcnow().isoformat())
    await hass.async_block_till_done()
    hass.states.async_set(GLUCOSE_ENTITY, "130", {"unit_of_measurement": "mg/dL"})
    await hass.async_block_till_done()
    assert hass.states.get(STATUS_SENSOR).attributes["rate"] == 4.0


async def test_rapid_alarms_need_known_data(scenario: Scenario) -> None:
    """Unknown trends, stale data or no rate limit start no rapid alarm."""
    await scenario.setup(
        high_options(rapid_rise=alarm(detection="rate", rate_entity=RATE_ENTITY))
    )
    scenario.hass.states.async_set(TREND_ENTITY, "not_computable")
    await scenario.wait(5, 200)  # no rate limit entity state
    assert scenario.phases() == []
    await scenario.wait(21)  # stale
    scenario.hass.states.async_set(TREND_ENTITY, "falling_quickly")
    await scenario.hass.async_block_till_done()
    assert ("rapid_fall", "triggered") not in scenario.phases()
