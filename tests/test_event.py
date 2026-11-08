"""Tests for the event entities of the alarms and the report."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.blood_glucose_monitor.const import BUILDER_URL, DOMAIN

from .test_alarms import Scenario, options


async def setup_scenario(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, **overrides: object
) -> tuple[Scenario, str]:
    """Set up an entry, return the scenario and the device ID."""
    scenario = Scenario(hass, freezer)
    await scenario.reading(110)
    await scenario.setup(options(**overrides))
    entry_id = scenario.entry.entry_id
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, entry_id), entry_id
    )
    assert device is not None
    return scenario, device.id


def event_types(hass: HomeAssistant, entity_id: str) -> list[str] | None:
    """Return the event types of an event entity, None without the entity."""
    state = hass.states.get(entity_id)
    return None if state is None else state.attributes["event_types"]


async def test_event_entities_of_enabled_alarms(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Each enabled alarm has an event entity; the report has its own."""
    # Urgent low without threshold is off.
    hass.states.async_set("input_boolean.period", "off")
    await setup_scenario(
        hass,
        freezer,
        urgent_low={"only_when_home": False},
        report={"report_entity": "input_boolean.period"},
    )
    assert event_types(hass, "event.alex_low_alarm") == ["low_alert", "low_ended"]
    assert event_types(hass, "event.alex_data_loss_alarm") == [
        "data_loss_alert",
        "data_loss_ended",
    ]
    assert event_types(hass, "event.alex_urgent_low_alarm") is None
    assert event_types(hass, "event.alex_report") == ["report"]
    assert hass.states.get("event.alex_alarm") is None


async def test_change_event_types(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Change reminders with a warning also have the "due soon" event type."""
    wear = {"days": 3}
    await setup_scenario(
        hass,
        freezer,
        cannula_change={"wear_duration": wear, "warning": {"hours": 12}},
        sensor_change={"wear_duration": wear},
        reservoir_change={"wear_duration": {"days": 0}},
    )
    assert event_types(hass, "event.alex_cannula_change_reminder") == [
        "cannula_change_alert",
        "cannula_change_ended",
        "cannula_change_soon",
    ]
    assert event_types(hass, "event.alex_sensor_change_reminder") == [
        "sensor_change_alert",
        "sensor_change_ended",
    ]
    assert event_types(hass, "event.alex_reservoir_change_reminder") is None
    assert hass.states.get("event.alex_report") is None


async def test_automation_on_device(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """An "Event received" automation on the device gets the alarm data."""
    scenario, device_id = await setup_scenario(hass, freezer)
    notify = async_capture_events(hass, "test_notify")
    clear = async_capture_events(hass, "test_clear")

    def automation(event_type: str, event: str) -> dict[str, object]:
        return {
            "triggers": [
                {
                    "trigger": "event.received",
                    "target": {"device_id": device_id},
                    "options": {"event_type": [event_type]},
                }
            ],
            "actions": [
                {
                    "event": event,
                    "event_data": {
                        "title": "{{ trigger.to_state.attributes.title }}",
                        "message": "{{ trigger.to_state.attributes.message }}",
                        "tag": "{{ trigger.to_state.attributes.tag }}",
                        "phase": "{{ trigger.to_state.attributes.phase }}",
                    },
                }
            ],
        }

    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": [
                automation("urgent_low_alert", "test_notify"),
                automation("urgent_low_ended", "test_clear"),
            ]
        },
    )
    # The low alarm (other event entity of the device) does not trigger.
    await scenario.reading(50)
    assert [event.data["phase"] for event in notify] == ["triggered"]
    assert notify[0].data["title"] == "Alex: urgent low glucose"
    assert notify[0].data["message"] == "50 mg/dL"

    await scenario.wait(5, 50)
    assert [event.data["phase"] for event in notify] == ["triggered", "repeat"]

    await hass.services.async_call(
        DOMAIN,
        "acknowledge",
        {"config_entry_id": scenario.entry.entry_id, "alarm": "urgent_low"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert [event.data["phase"] for event in clear] == ["acknowledged"]
    assert clear[0].data["tag"] == notify[0].data["tag"]


async def test_builder_links(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Device page and options menu link to the prefilled automation builder."""
    scenario, device_id = await setup_scenario(
        hass,
        freezer,
        cannula_change={"wear_duration": {"days": 3}, "warning": {"hours": 12}},
    )
    device = dr.async_get(hass).async_get(device_id)
    assert device is not None
    url = urlsplit(device.configuration_url)
    assert f"{url.scheme}://{url.netloc}{url.path}" == BUILDER_URL
    assert parse_qs(url.query) == {
        "name": ["Alex"],
        "urgent_low": ["event.alex_urgent_low_alarm"],
        "low": ["event.alex_low_alarm"],
        "data_loss": ["event.alex_data_loss_alarm"],
        "cannula_change": ["event.alex_cannula_change_reminder"],
        "soon": ["cannula_change"],
    }

    result = await hass.config_entries.options.async_init(scenario.entry.entry_id)
    assert result["description_placeholders"] == {
        "builder_url": device.configuration_url
    }
