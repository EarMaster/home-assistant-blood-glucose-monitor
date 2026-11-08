"""Scenario tests for the change reminders (synthetic data)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.blood_glucose_monitor.monitor import AlarmMonitor

from .test_alarms import PERSON, Scenario, alarm, options
from .test_charging_and_reports import local

CHANGED_BUTTON = "button.alex_cannula_changed"
DUE_SENSOR = "sensor.alex_cannula_change_due"
REMINDER_SENSOR = "sensor.alex_cannula_change_reminder"
LAST_CHANGE = "sensor.cannula_last_change"


def change_options(**overrides: Any) -> dict[str, Any]:
    """Return options with a cannula change reminder after 3 days."""
    settings: dict[str, Any] = {
        "wear_duration": {"days": 3, "hours": 0, "minutes": 0, "seconds": 0},
        "repeat": 0,
        "snooze": 60,
        **overrides,
    }
    return options(cannula_change=alarm(**settings))


def change_events(scenario: Scenario) -> list[dict[str, Any]]:
    """Return the events of the cannula change reminder."""
    return [
        event.data
        for event in scenario.events
        if event.data["type"].startswith("cannula_change_")
    ]


def phases(scenario: Scenario) -> list[str]:
    """Return the phases of the cannula change events."""
    return [data["phase"] for data in change_events(scenario)]


async def jump(scenario: Scenario, moment: datetime) -> None:
    """Move the time to ``moment`` and run the timers."""
    scenario.freezer.move_to(moment)
    async_fire_time_changed(scenario.hass, dt_util.as_utc(moment))
    await scenario.hass.async_block_till_done()


async def press(hass: HomeAssistant, entity_id: str) -> None:
    """Press a button."""
    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )


def due(hass: HomeAssistant) -> datetime | None:
    """Return the state of the due sensor."""
    state = hass.states.get(DUE_SENSOR)
    assert state is not None
    return dt_util.parse_datetime(state.state)


async def record_change(hass: HomeAssistant, entry_id: str, **data: Any) -> None:
    """Call the record change action."""
    await hass.services.async_call(
        "blood_glucose_monitor",
        "record_change",
        {"config_entry_id": entry_id, "change": "cannula_change", **data},
        blocking=True,
    )


@pytest.fixture
async def scenario(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> Scenario:
    """Return a scenario on November 6th, 08:00 local time."""
    freezer.move_to(local(8, day=6))
    scenario = Scenario(hass, freezer)
    await scenario.reading(110)
    return scenario


async def test_change_with_button(scenario: Scenario) -> None:
    """Changed button → due after the wear duration → reminder → next change."""
    hass = scenario.hass
    await scenario.setup(change_options())
    assert scenario.state(DUE_SENSOR) == "unknown"
    assert scenario.state(REMINDER_SENSOR) == "idle"

    await press(hass, CHANGED_BUTTON)
    assert due(hass) == local(8, day=9)
    attributes = hass.states.get(DUE_SENSOR).attributes
    assert attributes["last_change"] == dt_util.as_utc(local(8, day=6)).isoformat()
    assert attributes["wear_duration_h"] == 72

    await jump(scenario, local(7, 59, day=9))
    assert phases(scenario) == []
    await jump(scenario, local(8, day=9))
    assert phases(scenario) == ["triggered"]
    data = change_events(scenario)[-1]
    assert data["type"] == "cannula_change_alert"
    assert data["title"] == "Alex: change the cannula"
    assert data["message"] == "Worn for 72 h."
    assert data["due"] == dt_util.as_utc(local(8, day=9)).isoformat()
    assert scenario.state(REMINDER_SENSOR) == "active"

    await jump(scenario, local(9, day=9))
    await press(hass, CHANGED_BUTTON)
    assert phases(scenario) == ["triggered", "resolved"]
    assert change_events(scenario)[-1]["type"] == "cannula_change_ended"
    assert due(hass) == local(9, day=12)


async def test_fixed_time_on_due_day(scenario: Scenario) -> None:
    """With a fixed time the reminder starts at that time on the due day."""
    hass = scenario.hass
    await scenario.setup(change_options(due_time="18:00:00"))
    await jump(scenario, local(23, 40, day=6))
    await press(hass, CHANGED_BUTTON)
    assert due(hass) == local(18, day=9)
    await jump(scenario, local(17, 59, day=9))
    assert phases(scenario) == []
    await jump(scenario, local(18, day=9))
    assert phases(scenario) == ["triggered"]


async def test_fixed_time_entity(scenario: Scenario) -> None:
    """A time entity takes precedence; without a valid time no due time."""
    hass = scenario.hass
    hass.states.async_set("input_datetime.change_time", "19:30:00")
    await scenario.setup(
        change_options(due_time="18:00:00", time_entity="input_datetime.change_time")
    )
    await press(hass, CHANGED_BUTTON)
    assert due(hass) == local(19, 30, day=9)
    hass.states.async_set("input_datetime.change_time", "unknown")
    await hass.async_block_till_done()
    assert due(hass) is None


async def test_warning(scenario: Scenario) -> None:
    """The warning fires once; while away it waits until the person is home."""
    hass = scenario.hass
    await scenario.setup(change_options(warning={"hours": 12}, only_when_home=True))
    await press(hass, CHANGED_BUTTON)

    await jump(scenario, local(19, 59, day=8))
    assert phases(scenario) == []
    hass.states.async_set(PERSON, "not_home")
    await jump(scenario, local(20, day=8))
    await jump(scenario, local(22, day=8))
    assert phases(scenario) == []
    # Coming home sends the warning at once.
    hass.states.async_set(PERSON, "home")
    await hass.async_block_till_done()
    assert phases(scenario) == ["soon"]
    data = change_events(scenario)[-1]
    assert data["type"] == "cannula_change_soon"
    assert data["title"] == "Alex: cannula change due soon"
    assert data["message"] == "Due in 10 h."

    await jump(scenario, local(23, day=8))
    assert phases(scenario) == ["soon"]
    await jump(scenario, local(8, day=9))
    assert phases(scenario) == ["soon", "triggered"]


async def test_last_change_entity(scenario: Scenario) -> None:
    """With a last change entity only the entity counts: no button, no action."""
    hass = scenario.hass
    hass.states.async_set(LAST_CHANGE, dt_util.as_utc(local(6, day=6)).isoformat())
    await scenario.setup(change_options(last_change_entity=LAST_CHANGE))
    assert hass.states.get(CHANGED_BUTTON) is None
    assert due(hass) == local(6, day=9)
    with pytest.raises(ServiceValidationError) as error:
        await record_change(hass, scenario.entry.entry_id)
    assert error.value.translation_key == "change_from_entity"

    await jump(scenario, local(6, day=9))
    assert phases(scenario) == ["triggered"]
    hass.states.async_set(LAST_CHANGE, dt_util.as_utc(local(6, 30, day=9)).isoformat())
    await hass.async_block_till_done()
    assert phases(scenario) == ["triggered", "resolved"]
    assert due(hass) == local(6, 30, day=12)


async def test_wear_duration_entity(scenario: Scenario) -> None:
    """The wear duration entity takes precedence; its unit is required."""
    hass = scenario.hass
    hass.states.async_set("input_number.wear", "2", {"unit_of_measurement": "d"})
    await scenario.setup(change_options(wear_duration_entity="input_number.wear"))
    await press(hass, CHANGED_BUTTON)
    assert due(hass) == local(8, day=8)
    hass.states.async_set("input_number.wear", "36", {"unit_of_measurement": "h"})
    await hass.async_block_till_done()
    assert due(hass) == local(20, day=7)
    hass.states.async_set("input_number.wear", "36")
    await hass.async_block_till_done()
    assert due(hass) is None


async def test_record_change_action(scenario: Scenario) -> None:
    """The action records a change now or at a time in the past."""
    hass = scenario.hass
    await scenario.setup(change_options())
    entry_id = scenario.entry.entry_id
    await record_change(hass, entry_id, time="2026-11-05 22:00:00")
    assert due(hass) == local(22, day=8)
    await record_change(hass, entry_id)
    assert due(hass) == local(8, day=9)

    with pytest.raises(ServiceValidationError) as error:
        await record_change(hass, entry_id, time="2026-11-07 08:00:00")
    assert error.value.translation_key == "change_in_future"
    with pytest.raises(ServiceValidationError) as error:
        await hass.services.async_call(
            "blood_glucose_monitor",
            "record_change",
            {"config_entry_id": entry_id, "change": "sensor_change"},
            blocking=True,
        )
    assert error.value.translation_key == "change_not_enabled"


async def test_change_survives_restart(scenario: Scenario) -> None:
    """A recorded change and a sent warning are kept across a restart."""
    hass = scenario.hass
    await scenario.setup(change_options(warning={"hours": 12}))
    await press(hass, CHANGED_BUTTON)
    await jump(scenario, local(20, day=8))
    assert phases(scenario) == ["soon"]
    entry_id = scenario.entry.entry_id
    assert await hass.config_entries.async_unload(entry_id)
    assert await hass.config_entries.async_setup(entry_id)
    await hass.async_block_till_done()
    assert due(hass) == local(8, day=9)
    assert phases(scenario) == ["soon"]


async def test_without_glucose_reading_time(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """The change reminders do not need glucose data."""
    freezer.move_to(local(8, day=6))
    scenario = Scenario(hass, freezer)
    await scenario.setup(change_options())
    await press(hass, CHANGED_BUTTON)
    assert scenario.state(REMINDER_SENSOR) == "idle"
    await jump(scenario, local(8, day=9))
    assert phases(scenario) == ["triggered"]


def test_datetime_from_state() -> None:
    """Datetime, naive datetime and date states are understood."""
    parse = AlarmMonitor.datetime_from_state
    zone = dt_util.get_default_time_zone()
    assert parse("2026-11-06T07:00:00+00:00") == datetime(
        2026, 11, 6, 7, tzinfo=dt_util.UTC
    )
    assert parse("2026-11-06 08:00:00") == dt_util.as_utc(
        datetime(2026, 11, 6, 8, tzinfo=zone)
    )
    assert parse("2026-11-06") == dt_util.as_utc(datetime(2026, 11, 6, tzinfo=zone))
    assert parse("yesterday") is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"days": 1, "hours": 2}, timedelta(days=1, hours=2)),
        ({"days": 0, "hours": 0, "minutes": 0}, None),
        ({"days": "x"}, None),
        (None, None),
    ],
)
def test_duration(value: object, expected: timedelta | None) -> None:
    """Duration selector values become positive durations."""
    from custom_components.blood_glucose_monitor.monitor import duration

    assert duration(value) == expected
