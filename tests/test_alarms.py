"""Scenario tests for the alarms, with synthetic glucose data."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import EVENT_STATE_CHANGED, STATE_UNAVAILABLE
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.blood_glucose_monitor.const import (
    CONF_GLUCOSE_ENTITY,
    CONF_NAME,
    CONF_PERSON_ENTITY,
    CONF_READING_TIME_ENTITY,
    DOMAIN,
)

from .conftest import GLUCOSE_ENTITY, READING_TIME_ENTITY

LOW_THRESHOLD = "input_number.low_threshold"
URGENT_THRESHOLD = "input_number.urgent_threshold"
PERSON = "person.alex"

STATUS_SENSOR = "sensor.alex_status"
LOW_SENSOR = "sensor.alex_low_alarm"
URGENT_SENSOR = "sensor.alex_urgent_low_alarm"
DATA_LOSS_SENSOR = "sensor.alex_data_loss_alarm"
LOW_BUTTON = "button.alex_acknowledge_low_alarm"
PAUSE_SWITCH = "switch.alex_pause_alarms"
LOW_EVENT = "event.alex_low_alarm"
DATA_LOSS_EVENT = "event.alex_data_loss_alarm"


class Fired:
    """An event of an event entity of the integration."""

    def __init__(self, data: dict[str, Any]) -> None:
        """Initialize with the event type as "type" and the attributes."""
        self.data = data


def capture_fired(hass: HomeAssistant) -> list[Fired]:
    """Record the events of all event entities (not restored states)."""
    fired: list[Fired] = []

    @callback
    def listener(event: Event[EventStateChangedData]) -> None:
        new, old = event.data["new_state"], event.data["old_state"]
        if (
            new is None
            or new.domain != "event"
            or old is None
            or old.state == STATE_UNAVAILABLE
            or (event_type := new.attributes.get("event_type")) is None
        ):
            return
        fired.append(Fired({"type": event_type, **new.attributes}))

    hass.bus.async_listen(EVENT_STATE_CHANGED, listener)
    return fired


def alarm(**overrides: Any) -> dict[str, Any]:
    """Return alarm options."""
    return {"only_when_home": False, **overrides}


def options(**overrides: Any) -> dict[str, Any]:
    """Return entry options with all alarms enabled."""
    return {
        CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY,
        CONF_READING_TIME_ENTITY: READING_TIME_ENTITY,
        CONF_PERSON_ENTITY: PERSON,
        "urgent_low": alarm(
            threshold_entity=URGENT_THRESHOLD,
            clear_offset=5,
            delay=0,
            repeat=5,
            snooze=10,
        ),
        "low": alarm(
            threshold_entity=LOW_THRESHOLD,
            clear_offset=10,
            delay=5,
            repeat=5,
            snooze=15,
        ),
        "data_loss": alarm(max_age=20, repeat=15, snooze=30),
        "pause": {"duration": 60},
        **overrides,
    }


class Scenario:
    """Drive time and glucose readings, record the actions."""

    def __init__(self, hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
        """Initialize."""
        self.hass = hass
        self.freezer = freezer
        self.events = capture_fired(hass)

    @property
    def actions(self) -> list[Fired]:
        """Return the alarm events of the "started or repeated" triggers."""
        return [e for e in self.events if e.data["type"].endswith("_alert")]

    @property
    def ends(self) -> list[Fired]:
        """Return the alarm events of the "acknowledged or over" triggers."""
        return [e for e in self.events if e.data["type"].endswith("_ended")]

    async def setup(self, entry_options: dict[str, Any] | None = None) -> None:
        """Set thresholds and person, then set up an entry."""
        hass = self.hass
        hass.states.async_set(LOW_THRESHOLD, "70", {"unit_of_measurement": "mg/dL"})
        hass.states.async_set(URGENT_THRESHOLD, "55", {"unit_of_measurement": "mg/dL"})
        hass.states.async_set(PERSON, "home")
        self.entry = MockConfigEntry(
            domain=DOMAIN,
            title="Alex",
            data={CONF_NAME: "Alex"},
            options=entry_options or options(),
        )
        self.entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(self.entry.entry_id)
        await hass.async_block_till_done()

    async def reading(self, value: float) -> None:
        """Report a new reading now."""
        self.hass.states.async_set(
            GLUCOSE_ENTITY, str(value), {"unit_of_measurement": "mg/dL"}
        )
        self.hass.states.async_set(READING_TIME_ENTITY, dt_util.utcnow().isoformat())
        await self.hass.async_block_till_done()

    async def wait(self, minutes: float, value: float | None = None) -> None:
        """Let time pass, with a new reading every 5 minutes if given."""
        remaining = minutes
        while remaining > 0:
            step = min(5, remaining)
            self.freezer.tick(timedelta(minutes=step))
            async_fire_time_changed(self.hass)
            await self.hass.async_block_till_done()
            if value is not None:
                await self.reading(value)
            remaining -= step

    def phases(self, events: list[Fired] | None = None) -> list[tuple[str, str]]:
        """Return (alarm, phase) of the recorded action runs."""
        return [
            (event.data["alarm"], event.data["phase"])
            for event in (self.actions if events is None else events)
        ]

    def state(self, entity_id: str) -> str:
        """Return the state of an entity."""
        state = self.hass.states.get(entity_id)
        assert state is not None, entity_id
        return state.state


@pytest.fixture
async def scenario(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> Scenario:
    """Return a scenario with a first normal reading."""
    scenario = Scenario(hass, freezer)
    await scenario.reading(110)
    return scenario


async def test_short_dip_gives_no_alarm(scenario: Scenario) -> None:
    """A dip below the low threshold shorter than the delay gives no alarm."""
    await scenario.setup()
    await scenario.reading(68)
    assert scenario.state(LOW_SENSOR) == "pending"
    await scenario.wait(3)
    await scenario.reading(79)
    await scenario.wait(10, 79)
    assert scenario.actions == []
    assert scenario.state(LOW_SENSOR) == "idle"


async def test_low_alarm_acknowledge_and_recheck(scenario: Scenario) -> None:
    """Low alarm: delay, repeat, acknowledge, re-check after snooze, end."""
    await scenario.setup()
    await scenario.reading(65)
    await scenario.wait(5, 65)
    assert scenario.phases() == [("low", "triggered")]
    assert scenario.state(LOW_SENSOR) == "active"
    data = scenario.actions[0].data
    entry_id = scenario.entry.entry_id
    assert data["title"] == "Alex: low glucose"
    assert data["message"] == "65 mg/dL"
    assert data["glucose"] == 65
    assert data["tag"] == f"blood_glucose_monitor_{entry_id}_low"
    assert data["icon"] == "mdi:arrow-down-circle"
    assert data["ack_action"] == f"BLOOD_GLUCOSE_MONITOR_ACK_{entry_id}_low"
    state = scenario.hass.states.get(LOW_EVENT)
    assert state.attributes["event_type"] == "low_alert"
    assert state.attributes["phase"] == "triggered"
    assert state.attributes["title"] == "Alex: low glucose"

    await scenario.wait(5, 64)
    assert scenario.phases()[-1] == ("low", "repeat")

    await scenario.hass.services.async_call(
        "button", "press", {"entity_id": LOW_BUTTON}, blocking=True
    )
    await scenario.hass.async_block_till_done()
    assert scenario.phases(scenario.ends) == [("low", "acknowledged")]
    assert scenario.ends[0].data["message"] == "Acknowledged."
    assert scenario.state(LOW_SENSOR) == "snoozed"

    # Still low when the snooze ends: alarm again at once.
    actions_before = len(scenario.actions)
    await scenario.wait(15, 66)
    assert scenario.phases()[actions_before:] == [("low", "triggered")]

    # Between threshold and clear offset: the alarm continues.
    await scenario.reading(75)
    assert scenario.state(LOW_SENSOR) == "active"
    await scenario.reading(80)
    assert scenario.phases(scenario.ends)[-1] == ("low", "resolved")
    assert scenario.state(LOW_SENSOR) == "idle"


async def acknowledge(scenario: Scenario, alarm: str | None = None) -> None:
    """Acknowledge one alarm (or all) with the action."""
    data = {"config_entry_id": scenario.entry.entry_id}
    if alarm:
        data["alarm"] = alarm
    await scenario.hass.services.async_call(DOMAIN, "acknowledge", data, blocking=True)
    await scenario.hass.async_block_till_done()


async def test_urgent_low_holds_low(scenario: Scenario) -> None:
    """While urgent low runs, low neither starts nor repeats."""
    await scenario.setup()
    await scenario.reading(50)
    assert scenario.phases() == [("urgent_low", "triggered")]
    assert scenario.actions[0].data["title"] == "Alex: urgent low glucose"
    await scenario.wait(30, 50)
    assert {alarm for alarm, _ in scenario.phases()} == {"urgent_low"}
    assert scenario.state(LOW_SENSOR) == "idle"


async def test_urgent_low_silences_repeats_of_low(scenario: Scenario) -> None:
    """A running low alarm stops repeating once urgent low starts."""
    await scenario.setup()
    await scenario.reading(65)
    await scenario.wait(5, 65)
    assert scenario.phases() == [("low", "triggered")]
    await scenario.reading(50)
    actions_before = len(scenario.actions)
    await scenario.wait(20, 50)
    assert {alarm for alarm, _ in scenario.phases()[actions_before:]} == {"urgent_low"}


async def test_acknowledging_urgent_low_snoozes_low(scenario: Scenario) -> None:
    """Acknowledging urgent low silences low until the same snooze ends."""
    await scenario.setup()
    await scenario.reading(65)
    await scenario.wait(5, 65)
    await scenario.reading(50)
    await acknowledge(scenario, "urgent_low")
    assert scenario.state(URGENT_SENSOR) == "snoozed"
    assert scenario.state(LOW_SENSOR) == "snoozed"
    assert scenario.phases(scenario.ends) == [
        ("urgent_low", "acknowledged"),
        ("low", "acknowledged"),
    ]

    # Back above urgent low but still low: silent until urgent low's snooze
    # (10 minutes) ends, then low again.
    actions_before = len(scenario.actions)
    await scenario.wait(5, 62)
    assert scenario.phases()[actions_before:] == []
    await scenario.wait(5, 62)
    assert scenario.phases()[actions_before:] == [("low", "triggered")]


async def test_acknowledging_urgent_low_holds_idle_low(scenario: Scenario) -> None:
    """Low does not start after urgent low was acknowledged, within its snooze."""
    await scenario.setup()
    await scenario.reading(50)
    await acknowledge(scenario, "urgent_low")
    assert scenario.state(LOW_SENSOR) == "snoozed"
    assert scenario.phases(scenario.ends) == [("urgent_low", "acknowledged")]
    # Clear again: low ends quietly, without an "ended" event.
    await scenario.reading(90)
    assert scenario.state(LOW_SENSOR) == "idle"
    assert scenario.phases(scenario.ends) == [
        ("urgent_low", "acknowledged"),
        ("urgent_low", "resolved"),
    ]


async def test_acknowledging_low_does_not_hold_urgent_low(scenario: Scenario) -> None:
    """Urgent low still sounds when low was acknowledged before."""
    await scenario.setup()
    await scenario.reading(65)
    await scenario.wait(5, 65)
    await acknowledge(scenario, "low")
    assert scenario.state(LOW_SENSOR) == "snoozed"
    await scenario.reading(50)
    assert scenario.phases()[-1] == ("urgent_low", "triggered")
    assert scenario.state(URGENT_SENSOR) == "active"

    await acknowledge(scenario)
    assert scenario.state(URGENT_SENSOR) == "snoozed"


async def test_mobile_app_action_acknowledges(scenario: Scenario) -> None:
    """The notification action of the mobile app acknowledges the alarm."""
    await scenario.setup()
    await scenario.reading(50)
    ack_action = scenario.actions[0].data["ack_action"]
    scenario.hass.bus.async_fire("mobile_app_notification_action", {"action": "OTHER"})
    await scenario.hass.async_block_till_done()
    assert scenario.state(URGENT_SENSOR) == "active"
    scenario.hass.bus.async_fire(
        "mobile_app_notification_action", {"action": ack_action}
    )
    await scenario.hass.async_block_till_done()
    assert scenario.state(URGENT_SENSOR) == "snoozed"


async def test_entries_are_independent(scenario: Scenario) -> None:
    """Acknowledging the alarm of one entry does not touch another entry."""
    await scenario.setup()
    other = MockConfigEntry(
        domain=DOMAIN, title="Alex 2", data={CONF_NAME: "Alex 2"}, options=options()
    )
    other.add_to_hass(scenario.hass)
    assert await scenario.hass.config_entries.async_setup(other.entry_id)
    await scenario.reading(50)
    assert scenario.phases() == [("urgent_low", "triggered")] * 2
    await scenario.hass.services.async_call(
        DOMAIN, "acknowledge", {"config_entry_id": other.entry_id}, blocking=True
    )
    assert scenario.state(URGENT_SENSOR) == "active"
    assert scenario.state("sensor.alex_2_urgent_low_alarm") == "snoozed"
    tags = {event.data["tag"] for event in scenario.actions}
    assert len(tags) == 2


async def test_data_loss(scenario: Scenario) -> None:
    """Missing data starts the data loss alarm and holds the low alarm."""
    await scenario.setup()
    await scenario.reading(65)
    await scenario.wait(5, 65)
    assert scenario.phases() == [("low", "triggered")]

    # Exactly the maximum age is not yet data loss.
    await scenario.wait(20)
    assert ("data_loss", "triggered") not in scenario.phases()
    await scenario.wait(1)
    assert ("data_loss", "triggered") in scenario.phases()
    data_loss = next(e for e in scenario.actions if e.data["alarm"] == "data_loss")
    assert data_loss.data["title"] == "Alex: no glucose data"
    assert data_loss.data["message"] == "No new reading for 21 min."
    # Stale data neither ends nor (here) re-triggers the low alarm.
    assert scenario.state(LOW_SENSOR) == "active"

    await scenario.reading(90)
    assert ("data_loss", "resolved") in scenario.phases(scenario.ends)
    assert ("low", "resolved") in scenario.phases(scenario.ends)


async def test_glucose_unavailable_counts_as_data_loss(scenario: Scenario) -> None:
    """An unavailable glucose sensor is data loss after the maximum age."""
    await scenario.setup()
    scenario.hass.states.async_set(GLUCOSE_ENTITY, STATE_UNAVAILABLE)
    scenario.hass.states.async_set(READING_TIME_ENTITY, STATE_UNAVAILABLE)
    await scenario.wait(21)
    assert scenario.phases() == [("data_loss", "triggered")]


async def test_pause(scenario: Scenario) -> None:
    """The pause silences low and data loss, never urgent low."""
    await scenario.setup()
    await scenario.reading(65)
    await scenario.wait(5, 65)
    await scenario.hass.services.async_call(
        "switch", "turn_on", {"entity_id": PAUSE_SWITCH}, blocking=True
    )
    assert scenario.state(PAUSE_SWITCH) == "on"
    assert scenario.phases(scenario.ends) == [("low", "acknowledged")]

    await scenario.reading(50)
    assert ("urgent_low", "triggered") in scenario.phases()
    await scenario.reading(65)

    # The pause ends by itself; the low alarm is checked again at once.
    before = len(scenario.actions)
    await scenario.wait(60, 65)
    assert scenario.state(PAUSE_SWITCH) == "off"
    assert ("low", "triggered") in scenario.phases()[before:]


async def test_pause_turned_off(scenario: Scenario) -> None:
    """Turning the pause off checks the alarms again at once."""
    await scenario.setup()
    await scenario.reading(65)
    await scenario.wait(5, 65)
    await scenario.hass.services.async_call(
        "switch", "turn_on", {"entity_id": PAUSE_SWITCH}, blocking=True
    )
    await scenario.hass.services.async_call(
        "switch", "turn_off", {"entity_id": PAUSE_SWITCH}, blocking=True
    )
    assert scenario.phases()[-1] == ("low", "triggered")


PAUSE_ENTITY = "schedule.school"


async def test_pause_entity(scenario: Scenario) -> None:
    """While the pause entity is on, all alarms except urgent low are paused."""
    hass = scenario.hass
    hass.states.async_set(PAUSE_ENTITY, "off")
    await scenario.setup(
        options(pause={"duration": 60, "pause_entities": [PAUSE_ENTITY]})
    )
    await scenario.reading(65)
    await scenario.wait(5, 65)
    assert scenario.phases() == [("low", "triggered")]

    hass.states.async_set(PAUSE_ENTITY, "on")
    await hass.async_block_till_done()
    assert scenario.phases(scenario.ends) == [("low", "acknowledged")]
    assert scenario.state(PAUSE_SWITCH) == "on"
    assert scenario.state(STATUS_SENSOR) == "paused"
    assert scenario.hass.states.get(PAUSE_SWITCH).attributes["until"] is None
    await scenario.wait(30, 65)
    assert scenario.state(LOW_SENSOR) == "idle"
    assert scenario.phases() == [("low", "triggered")]
    await scenario.reading(50)
    assert scenario.phases()[-1] == ("urgent_low", "triggered")
    await scenario.reading(90)

    # Off again: a new low starts with its delay.
    await scenario.reading(65)
    hass.states.async_set(PAUSE_ENTITY, "off")
    await hass.async_block_till_done()
    assert scenario.state(PAUSE_SWITCH) == "off"
    assert scenario.state(LOW_SENSOR) == "pending"
    await scenario.wait(5, 65)
    assert scenario.phases()[-1] == ("low", "triggered")


async def test_several_pause_entities(scenario: Scenario) -> None:
    """The alarms are paused while any of the pause entities is on."""
    hass = scenario.hass
    trip = "input_boolean.trip"
    hass.states.async_set(PAUSE_ENTITY, "on")
    hass.states.async_set(trip, "off")
    await scenario.setup(
        options(pause={"duration": 60, "pause_entities": [PAUSE_ENTITY, trip]})
    )
    hass.states.async_set(trip, "on")
    hass.states.async_set(PAUSE_ENTITY, "off")
    await scenario.reading(65)
    await scenario.wait(10, 65)
    assert scenario.phases() == []
    assert scenario.state(PAUSE_SWITCH) == "on"

    hass.states.async_set(trip, "off")
    await scenario.wait(5, 65)
    assert scenario.phases() == [("low", "triggered")]


async def test_pause_entity_unknown(scenario: Scenario) -> None:
    """An unavailable pause entity pauses nothing."""
    scenario.hass.states.async_set(PAUSE_ENTITY, STATE_UNAVAILABLE)
    await scenario.setup(
        options(pause={"duration": 60, "pause_entities": [PAUSE_ENTITY]})
    )
    await scenario.reading(65)
    await scenario.wait(5, 65)
    assert scenario.phases() == [("low", "triggered")]


async def test_only_when_home(scenario: Scenario) -> None:
    """With the home option, new alarms only start while the person is home."""
    entry_options = options()
    entry_options["urgent_low"]["only_when_home"] = True
    await scenario.setup(entry_options)
    scenario.hass.states.async_set(PERSON, "not_home")
    await scenario.reading(50)
    assert scenario.phases() == []
    scenario.hass.states.async_set(PERSON, "home")
    await scenario.hass.async_block_till_done()
    assert scenario.phases() == [("urgent_low", "triggered")]
    # A running alarm continues when the person leaves.
    scenario.hass.states.async_set(PERSON, "not_home")
    await scenario.wait(5, 50)
    assert ("urgent_low", "repeat") in scenario.phases()


async def test_restart_during_alarm(scenario: Scenario) -> None:
    """An active alarm survives a restart and keeps repeating."""
    await scenario.setup()
    await scenario.reading(50)
    hass = scenario.hass
    assert await hass.config_entries.async_reload(scenario.entry.entry_id)
    await hass.async_block_till_done()
    assert scenario.state(URGENT_SENSOR) == "active"
    assert scenario.phases() == [("urgent_low", "triggered")]
    await scenario.wait(5, 50)
    assert ("urgent_low", "repeat") in scenario.phases()


async def test_no_data_loss_right_after_restart(scenario: Scenario) -> None:
    """After a long downtime the source gets the maximum data age to deliver."""
    await scenario.setup()
    hass = scenario.hass
    assert await hass.config_entries.async_unload(scenario.entry.entry_id)
    scenario.freezer.tick(timedelta(hours=2))
    hass.states.async_set(GLUCOSE_ENTITY, STATE_UNAVAILABLE)
    hass.states.async_set(READING_TIME_ENTITY, STATE_UNAVAILABLE)
    assert await hass.config_entries.async_setup(scenario.entry.entry_id)
    await hass.async_block_till_done()
    assert scenario.phases() == []
    await scenario.wait(20)
    assert scenario.phases() == []
    await scenario.wait(1)
    assert scenario.phases() == [("data_loss", "triggered")]


async def test_no_reading_time_no_alarms(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Without a reading time there are no alarms, and a repair issue."""
    scenario = Scenario(hass, freezer)
    hass.states.async_set(GLUCOSE_ENTITY, "50", {"unit_of_measurement": "mg/dL"})
    await scenario.setup(options(**{CONF_READING_TIME_ENTITY: ""}))
    assert scenario.state(URGENT_SENSOR) == STATE_UNAVAILABLE
    await scenario.wait(30)
    assert scenario.actions == []
    issue_id = f"no_reading_time_{scenario.entry.entry_id}"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id)

    hass.states.async_set(
        GLUCOSE_ENTITY,
        "50",
        {"unit_of_measurement": "mg/dL", "date": dt_util.utcnow().isoformat()},
    )
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
    assert scenario.phases() == [("urgent_low", "triggered")]


async def test_mmol_threshold_and_variables(scenario: Scenario) -> None:
    """Thresholds and variables work in mmol/L."""
    hass = scenario.hass
    await scenario.setup()
    hass.states.async_set(URGENT_THRESHOLD, "3.1", {"unit_of_measurement": "mmol/L"})
    hass.states.async_set(GLUCOSE_ENTITY, "2.9", {"unit_of_measurement": "mmol/L"})
    hass.states.async_set(READING_TIME_ENTITY, dt_util.utcnow().isoformat())
    await hass.async_block_till_done()
    assert scenario.phases() == [("urgent_low", "triggered")]
    data = scenario.actions[0].data
    assert data["glucose"] == 2.9
    assert data["unit"] == "mmol/L"
    assert data["message"] == "2.9 mmol/L"


async def test_threshold_as_number(scenario: Scenario) -> None:
    """A threshold can be a number in the unit of the glucose data."""
    await scenario.setup(
        options(
            urgent_low=alarm(threshold=55, clear_offset=5, delay=0, repeat=5, snooze=10)
        )
    )
    assert scenario.state(URGENT_SENSOR) == "idle"
    await scenario.reading(54)
    assert scenario.phases() == [("urgent_low", "triggered")]


async def test_threshold_number_in_mmol(scenario: Scenario) -> None:
    """The number is read in the unit of the glucose data (mmol/L here)."""
    hass = scenario.hass
    await scenario.setup(
        options(
            urgent_low=alarm(
                threshold=3.1, clear_offset=0.3, delay=0, repeat=5, snooze=10
            )
        )
    )
    hass.states.async_set(GLUCOSE_ENTITY, "3.2", {"unit_of_measurement": "mmol/L"})
    hass.states.async_set(READING_TIME_ENTITY, dt_util.utcnow().isoformat())
    await hass.async_block_till_done()
    assert scenario.phases() == []
    hass.states.async_set(GLUCOSE_ENTITY, "3.0", {"unit_of_measurement": "mmol/L"})
    hass.states.async_set(READING_TIME_ENTITY, dt_util.utcnow().isoformat())
    await hass.async_block_till_done()
    assert scenario.phases() == [("urgent_low", "triggered")]


async def test_threshold_entity_wins(scenario: Scenario) -> None:
    """With both, the threshold entity counts and the number is ignored."""
    await scenario.setup(
        options(
            urgent_low=alarm(
                threshold=80,
                threshold_entity=URGENT_THRESHOLD,
                clear_offset=5,
                delay=0,
                repeat=5,
                snooze=10,
            )
        )
    )
    await scenario.reading(60)
    assert ("urgent_low", "triggered") not in scenario.phases()
    await scenario.reading(54)
    assert ("urgent_low", "triggered") in scenario.phases()


async def test_unavailable_threshold_holds(scenario: Scenario) -> None:
    """Without a threshold value the alarm neither starts nor ends."""
    await scenario.setup()
    scenario.hass.states.async_set(URGENT_THRESHOLD, STATE_UNAVAILABLE)
    await scenario.reading(40)
    assert scenario.phases() == []


async def test_alarms_without_threshold_are_off(scenario: Scenario) -> None:
    """Alarms without threshold have no entities; data loss is always active."""
    await scenario.setup(
        {
            CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY,
            CONF_READING_TIME_ENTITY: READING_TIME_ENTITY,
            "low": {"only_when_home": False},
        }
    )
    hass = scenario.hass
    assert hass.states.get(LOW_SENSOR) is None
    assert hass.states.get(URGENT_SENSOR) is None
    assert scenario.state(DATA_LOSS_SENSOR) == "idle"
    assert hass.states.get(LOW_EVENT) is None
    assert scenario.state(DATA_LOSS_EVENT) == "unknown"
    assert scenario.state(PAUSE_SWITCH) == "off"
    await scenario.reading(40)
    assert scenario.events == []


async def test_status(scenario: Scenario) -> None:
    """The status shows the most important running alarm."""
    hass = scenario.hass
    await scenario.setup()
    assert scenario.state(STATUS_SENSOR) == "ok"
    attributes = hass.states.get(STATUS_SENSOR).attributes
    assert attributes["glucose"] == 110
    assert attributes["unit"] == "mg/dL"
    assert attributes["active_alarms"] == []

    await scenario.reading(65)
    assert scenario.state(STATUS_SENSOR) == "ok"  # still pending
    await scenario.wait(5, 65)
    assert scenario.state(STATUS_SENSOR) == "low"
    await scenario.reading(50)
    assert scenario.state(STATUS_SENSOR) == "urgent_low"
    attributes = hass.states.get(STATUS_SENSOR).attributes
    assert attributes["active_alarms"] == ["urgent_low", "low"]

    await hass.services.async_call(
        DOMAIN,
        "acknowledge",
        {"config_entry_id": scenario.entry.entry_id},
        blocking=True,
    )
    assert scenario.state(STATUS_SENSOR) == "urgent_low"
    assert hass.states.get(STATUS_SENSOR).attributes["snoozed_alarms"] == [
        "urgent_low",
        "low",
    ]

    await scenario.reading(120)
    assert scenario.state(STATUS_SENSOR) == "ok"
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": PAUSE_SWITCH}, blocking=True
    )
    assert scenario.state(STATUS_SENSOR) == "paused"
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": PAUSE_SWITCH}, blocking=True
    )

    # Stale data is "no data" at once, before the data loss alarm.
    await scenario.wait(21)
    assert scenario.state(STATUS_SENSOR) == "no_data"


async def test_acknowledge_service_errors(scenario: Scenario) -> None:
    """The service reports unknown and unloaded entries."""
    await scenario.setup()
    hass = scenario.hass
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "acknowledge", {"config_entry_id": "nope"}, blocking=True
        )
    await hass.config_entries.async_unload(scenario.entry.entry_id)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "acknowledge",
            {"config_entry_id": scenario.entry.entry_id},
            blocking=True,
        )


async def test_remove_entry(scenario: Scenario) -> None:
    """Removing an entry removes its stored state."""
    await scenario.setup()
    hass = scenario.hass
    assert await hass.config_entries.async_remove(scenario.entry.entry_id)
    await hass.async_block_till_done()
