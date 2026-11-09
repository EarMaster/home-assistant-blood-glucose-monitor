"""The automation of the builder (site/builder.js) works with the event entities."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import parse_yaml
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.blood_glucose_monitor.const import DOMAIN

from .test_alarms import Scenario, options

# Output of the builder for Alex: urgent low started/ended, low started and
# the report, notify action notify.test_phone.
BUILDER_YAML = """
alias: "Blood glucose notifications: Alex"
description: "Created with the Blood Glucose Monitor automation builder."
mode: queued
triggers:
  - trigger: event.received
    alias: "Urgent low alarm started or repeated"
    id: urgent_low_alert
    target:
      entity_id: event.alex_urgent_low_alarm
    options:
      event_type:
        - urgent_low_alert
  - trigger: event.received
    alias: "Low alarm started or repeated"
    id: low_alert
    target:
      entity_id: event.alex_low_alarm
    options:
      event_type:
        - low_alert
  - trigger: event.received
    alias: "Urgent low alarm acknowledged or over"
    id: urgent_low_ended
    target:
      entity_id: event.alex_urgent_low_alarm
    options:
      event_type:
        - urgent_low_ended
  - trigger: event.received
    alias: "Report created"
    id: report
    target:
      entity_id: event.alex_report
    options:
      event_type:
        - report
variables:
  event: "{{ trigger.to_state.attributes if trigger.to_state is defined else {} }}"
actions:
  - choose:
      - conditions:
          - condition: trigger
            id:
              - urgent_low_alert
              - low_alert
        sequence:
          - action: notify.test_phone
            data:
              title: "{{ event.title }}"
              message: "{{ event.message }}"
              data:
                tag: "{{ event.tag }}"
                notification_icon: "{{ event.icon }}"
                channel: "{{ event.person_name }}"
                importance: high
                actions:
                  - action: "{{ event.ack_action }}"
                    title: "Acknowledge"
      - conditions:
          - condition: trigger
            id:
              - urgent_low_ended
        sequence:
          - action: notify.test_phone
            data:
              message: clear_notification
              data:
                tag: "{{ event.tag }}"
      - conditions:
          - condition: trigger
            id:
              - report
        sequence:
          - action: notify.test_phone
            data:
              title: "{{ event.title }}"
              message: "{{ event.message }}"
              data:
                tag: "{{ event.tag }}"
                notification_icon: "{{ event.icon }}"
                channel: "{{ event.person_name }}"
"""


async def test_builder_automation(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Alerts notify with acknowledge, ended clears, the report notifies."""
    hass.states.async_set("input_boolean.period", "off")
    scenario = Scenario(hass, freezer)
    await scenario.reading(110)
    await scenario.setup(options(report={"report_entity": "input_boolean.period"}))
    calls = async_mock_service(hass, "notify", "test_phone")
    assert await async_setup_component(
        hass, "automation", {"automation": [parse_yaml(BUILDER_YAML)]}
    )
    hass.states.async_set("input_boolean.period", "on")
    await scenario.reading(65)
    await scenario.wait(5, 65)
    entry_id = scenario.entry.entry_id
    assert calls[-1].data["title"] == "Alex: low glucose"

    await scenario.reading(50)
    assert calls[-1].data["title"] == "Alex: urgent low glucose"
    assert calls[-1].data["data"]["importance"] == "high"
    assert calls[-1].data["data"]["actions"][0]["action"] == (
        f"BLOOD_GLUCOSE_MONITOR_ACK_{entry_id}_urgent_low"
    )

    # The automation clears only urgent low (low_ended is not selected).
    count = len(calls)
    await hass.services.async_call(
        DOMAIN,
        "acknowledge",
        {"config_entry_id": entry_id, "alarm": "urgent_low"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert [call.data for call in calls[count:]] == [
        {
            "message": "clear_notification",
            "data": {"tag": f"blood_glucose_monitor_{entry_id}_urgent_low"},
        }
    ]

    count = len(calls)
    hass.states.async_set("input_boolean.period", "off")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(calls) == count + 1
    assert calls[-1].data["title"] == "Alex: report"
    assert calls[-1].data["data"] == {
        "tag": f"blood_glucose_monitor_{entry_id}_report",
        "notification_icon": "mdi:clipboard-text-clock",
        "channel": "Alex",
    }
