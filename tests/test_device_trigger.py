"""Tests for the device triggers of the alarms."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.device_automation import (
    DeviceAutomationType,
    async_get_device_automations,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.blood_glucose_monitor import device_trigger
from custom_components.blood_glucose_monitor.const import DOMAIN

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


async def test_triggers_of_enabled_alarms(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Each enabled alarm offers an alert and an ended trigger."""
    # Urgent low without threshold is off.
    _, device_id = await setup_scenario(
        hass, freezer, urgent_low={"only_when_home": False}
    )
    triggers = await async_get_device_automations(
        hass, DeviceAutomationType.TRIGGER, [device_id]
    )
    assert {
        trigger["type"]
        for trigger in triggers[device_id]
        if trigger["domain"] == DOMAIN
    } == {"low_alert", "low_ended", "data_loss_alert", "data_loss_ended"}
    assert await device_trigger.async_get_triggers(hass, "unknown") == []


async def test_automation_with_triggers(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Automations get the alarm data from the trigger."""
    scenario, device_id = await setup_scenario(hass, freezer)
    notify = async_capture_events(hass, "test_notify")
    clear = async_capture_events(hass, "test_clear")

    def automation(trigger_type: str, event: str) -> dict[str, object]:
        return {
            "triggers": [
                {
                    "trigger": "device",
                    "domain": DOMAIN,
                    "device_id": device_id,
                    "type": trigger_type,
                }
            ],
            "actions": [
                {
                    "event": event,
                    "event_data": {
                        "title": "{{ trigger.event.data.title }}",
                        "message": "{{ trigger.event.data.message }}",
                        "tag": "{{ trigger.event.data.tag }}",
                        "phase": "{{ trigger.event.data.phase }}",
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
