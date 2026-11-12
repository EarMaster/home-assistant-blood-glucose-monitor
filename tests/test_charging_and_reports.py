"""Scenario tests for the charging reminder and the reports (synthetic data)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
import pytest

from .test_alarms import PERSON, Scenario, acknowledge, alarm, options

BATTERY = "sensor.phone_battery_level"
CHARGING = "sensor.phone_battery_state"
REPORT_ENTITY = "input_boolean.report_period"
CHARGING_SENSOR = "sensor.alex_charging_reminder"
LAST_REPORT = "sensor.alex_last_report"


def charging_options(**overrides: Any) -> dict[str, Any]:
    """Return options with the charging reminder at 20:00."""
    settings: dict[str, Any] = {
        "battery_entity": BATTERY,
        "charging_entity": CHARGING,
        "reminder_time": "20:00:00",
        "battery_limit": 75,
        "repeat": 0,
        "snooze": 30,
        **overrides,
    }
    return options(charging=alarm(**settings))


def local(hour: int, minute: int = 0, day: int = 7) -> datetime:
    """Return a local time on November 7th (or ``day``) 2026."""
    return datetime(2026, 11, day, hour, minute, tzinfo=dt_util.get_default_time_zone())


@pytest.fixture
async def scenario(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> Scenario:
    """Return a scenario at 19:50 local time with a discharging phone."""
    freezer.move_to(local(19, 50))
    hass.states.async_set(BATTERY, "70", {"unit_of_measurement": "%"})
    hass.states.async_set(CHARGING, "discharging")
    scenario = Scenario(hass, freezer)
    await scenario.reading(110)
    return scenario


def charging_phases(scenario: Scenario) -> list[tuple[str, str]]:
    """Return the phases of the charging reminder."""
    return [
        phase for phase in scenario.phases(scenario.events) if phase[0] == "charging"
    ]


async def test_charging_reminder(scenario: Scenario) -> None:
    """Reminder at the time while not charging; ends when charging."""
    await scenario.setup(charging_options())
    assert scenario.state(CHARGING_SENSOR) == "idle"
    await scenario.wait(10, 110)
    assert charging_phases(scenario) == [("charging", "triggered")]
    data = scenario.actions[-1].data
    assert data["title"] == "Alex: charge the phone"
    assert data["message"] == "Battery at 70 % and not charging."
    assert data["battery"] == 70

    scenario.hass.states.async_set(CHARGING, "Charging")
    await scenario.hass.async_block_till_done()
    assert charging_phases(scenario)[-1] == ("charging", "resolved")


async def test_charging_battery_above_limit(scenario: Scenario) -> None:
    """Above the limit no reminder; when it drops later the same evening, one."""
    scenario.hass.states.async_set(BATTERY, "80", {"unit_of_measurement": "%"})
    await scenario.setup(charging_options())
    await scenario.wait(15, 110)
    assert charging_phases(scenario) == []
    scenario.hass.states.async_set(BATTERY, "75", {"unit_of_measurement": "%"})
    await scenario.hass.async_block_till_done()
    assert charging_phases(scenario) == [("charging", "triggered")]


async def test_charging_entities_take_precedence(scenario: Scenario) -> None:
    """Time and limit entities take precedence over the fields."""
    hass = scenario.hass
    hass.states.async_set("input_datetime.reminder", "20:30:00")
    hass.states.async_set("input_number.battery_limit", "60")
    await scenario.setup(
        charging_options(
            time_entity="input_datetime.reminder",
            battery_limit_entity="input_number.battery_limit",
        )
    )
    await scenario.wait(25, 110)  # 20:15
    assert charging_phases(scenario) == []
    hass.states.async_set("input_number.battery_limit", "70")
    await scenario.wait(20, 110)  # 20:35
    assert charging_phases(scenario) == [("charging", "triggered")]


async def test_charging_after_midnight(scenario: Scenario) -> None:
    """After midnight no new reminder starts; a running one waits for charging."""
    hass = scenario.hass
    scenario.freezer.move_to(local(23, 50))
    await scenario.setup(charging_options(repeat=30))
    assert charging_phases(scenario) == [("charging", "triggered")]
    await scenario.wait(40, 110)  # 00:30, repeat continues
    assert charging_phases(scenario)[-1] == ("charging", "repeat")
    hass.states.async_set(CHARGING, "full")
    await hass.async_block_till_done()
    assert charging_phases(scenario)[-1] == ("charging", "resolved")
    hass.states.async_set(CHARGING, "discharging")
    await scenario.wait(60, 110)
    assert charging_phases(scenario)[-1] == ("charging", "resolved")


async def test_charging_binary_sensor_and_unknown(scenario: Scenario) -> None:
    """A binary sensor works; an unknown charging state starts nothing."""
    hass = scenario.hass
    hass.states.async_set("binary_sensor.phone_is_charging", "on")
    await scenario.setup(
        charging_options(charging_entity="binary_sensor.phone_is_charging")
    )
    await scenario.wait(15, 110)
    assert charging_phases(scenario) == []
    hass.states.async_set("binary_sensor.phone_is_charging", "weird")
    await hass.async_block_till_done()
    assert charging_phases(scenario) == []
    hass.states.async_set("binary_sensor.phone_is_charging", "off")
    await hass.async_block_till_done()
    assert charging_phases(scenario) == [("charging", "triggered")]


async def test_charging_without_glucose_reading_time(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """The charging reminder does not need glucose data."""
    freezer.move_to(local(20, 5))
    hass.states.async_set(BATTERY, "50", {"unit_of_measurement": "%"})
    hass.states.async_set(CHARGING, "discharging")
    scenario = Scenario(hass, freezer)
    await scenario.setup(charging_options())
    assert charging_phases(scenario) == [("charging", "triggered")]


def report_events(scenario: Scenario) -> list[dict[str, Any]]:
    """Return the data of the report triggers."""
    return [e.data for e in scenario.events if e.data["type"] == "report"]


async def test_report_period(scenario: Scenario) -> None:
    """A period of the report entity gives a report with start, end and alarms."""
    hass = scenario.hass
    hass.states.async_set(REPORT_ENTITY, "off")
    await scenario.setup(options(report={"report_entity": REPORT_ENTITY}))
    assert scenario.state(LAST_REPORT) == "unknown"

    hass.states.async_set(REPORT_ENTITY, "on")
    await hass.async_block_till_done()
    start = dt_util.utcnow()
    await scenario.reading(65)
    await scenario.wait(5, 65)  # low alarm
    await scenario.wait(25, 110)
    hass.states.async_set(REPORT_ENTITY, "off")
    await hass.async_block_till_done(wait_background_tasks=True)

    reports = report_events(scenario)
    assert len(reports) == 1
    report = reports[0]
    assert report["start"] == start.isoformat()
    assert report["end"] == dt_util.utcnow().isoformat()
    assert report["duration_min"] == 30
    assert report["alarms"] == {"low": 1}
    assert report["low_alarms"] == 1
    assert report["title"] == "Alex: report"
    # No recorder in this test: no statistics.
    assert report["glucose_mean"] is None
    assert report["message"] == "19:50–20:20: no glucose data."
    assert hass.states.get(LAST_REPORT).attributes["low_alarms"] == 1


async def test_report_counts_lows_once(scenario: Scenario) -> None:
    """Repeats, re-checks and low ↔ urgent low belong to one low."""
    hass = scenario.hass
    hass.states.async_set(REPORT_ENTITY, "on")
    await scenario.setup(options(report={"report_entity": REPORT_ENTITY}))

    # First low: repeat, acknowledge, re-check after the snooze, urgent low,
    # back to low, over.
    await scenario.reading(65)
    await scenario.wait(5, 65)
    await scenario.wait(5, 64)
    await acknowledge(scenario, "low")
    await scenario.wait(15, 66)
    await scenario.reading(50)
    await scenario.wait(5, 50)
    await scenario.reading(62)
    await scenario.reading(85)
    assert scenario.phases() == [
        ("low", "triggered"),
        ("low", "repeat"),
        ("low", "triggered"),
        ("urgent_low", "triggered"),
        ("urgent_low", "repeat"),
    ]

    # Second low, after the cooldown.
    await scenario.wait(20, 110)
    await scenario.reading(65)
    await scenario.wait(5, 65)
    await scenario.reading(90)

    # Third low: urgent low first, low starts when urgent low is over.
    await scenario.wait(20, 110)
    await scenario.reading(50)
    await scenario.reading(62)
    await scenario.wait(5, 62)
    assert scenario.phases()[-2:] == [
        ("urgent_low", "triggered"),
        ("low", "triggered"),
    ]
    await scenario.reading(90)

    hass.states.async_set(REPORT_ENTITY, "off")
    await hass.async_block_till_done(wait_background_tasks=True)
    report = report_events(scenario)[0]
    assert report["alarms"] == {"low": 3, "urgent_low": 2}
    assert report["low_alarms"] == 3


@pytest.mark.parametrize(("cooldown", "lows"), [(None, 1), (5, 2), (0, 2)])
async def test_report_cooldown(
    scenario: Scenario, cooldown: int | None, lows: int
) -> None:
    """A low that starts again within the cooldown (15 minutes) is the same."""
    hass = scenario.hass
    hass.states.async_set(REPORT_ENTITY, "on")
    report: dict[str, Any] = {"report_entity": REPORT_ENTITY}
    if cooldown is not None:
        report["cooldown"] = cooldown
    await scenario.setup(options(report=report))
    await scenario.reading(65)
    await scenario.wait(5, 65)
    await scenario.reading(90)
    # Low again 10 minutes after the first one was over.
    await scenario.wait(5, 90)
    await scenario.reading(65)
    await scenario.wait(5, 65)
    assert scenario.phases() == [("low", "triggered"), ("low", "triggered")]
    await scenario.reading(90)
    hass.states.async_set(REPORT_ENTITY, "off")
    await hass.async_block_till_done(wait_background_tasks=True)
    data = report_events(scenario)[0]
    assert data["alarms"] == {"low": lows}
    assert data["low_alarms"] == lows


async def test_report_low_across_periods(scenario: Scenario) -> None:
    """A low that started before the period does not count in the period."""
    hass = scenario.hass
    hass.states.async_set(REPORT_ENTITY, "off")
    await scenario.setup(options(report={"report_entity": REPORT_ENTITY}))
    await scenario.reading(65)
    await scenario.wait(5, 65)
    await acknowledge(scenario, "low")
    hass.states.async_set(REPORT_ENTITY, "on")
    # Re-check after the snooze: the same low.
    await scenario.wait(15, 66)
    assert scenario.phases()[-1] == ("low", "triggered")
    await scenario.reading(90)
    hass.states.async_set(REPORT_ENTITY, "off")
    await hass.async_block_till_done(wait_background_tasks=True)
    report = report_events(scenario)[0]
    assert report["alarms"] == {}
    assert report["low_alarms"] == 0


async def test_report_only_when_home(scenario: Scenario) -> None:
    """Away: no report trigger, but the last report sensor is updated."""
    hass = scenario.hass
    hass.states.async_set(REPORT_ENTITY, "on")
    await scenario.setup(
        options(report={"report_entity": REPORT_ENTITY, "only_when_home": True})
    )
    hass.states.async_set(PERSON, "not_home")
    await scenario.wait(30, 110)
    hass.states.async_set(REPORT_ENTITY, "off")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert report_events(scenario) == []
    assert hass.states.get(LAST_REPORT).attributes["duration_min"] == 30

    hass.states.async_set(PERSON, "home")
    hass.states.async_set(REPORT_ENTITY, "on")
    await scenario.wait(30, 110)
    hass.states.async_set(REPORT_ENTITY, "off")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(report_events(scenario)) == 1


async def test_report_across_restart(scenario: Scenario) -> None:
    """A period that ends while the entry is not loaded is reported at start."""
    hass = scenario.hass
    hass.states.async_set(REPORT_ENTITY, "on")
    await scenario.setup(options(report={"report_entity": REPORT_ENTITY}))
    assert await hass.config_entries.async_unload(scenario.entry.entry_id)
    await scenario.wait(30)
    hass.states.async_set(REPORT_ENTITY, "off")
    assert await hass.config_entries.async_setup(scenario.entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(report_events(scenario)) == 1
