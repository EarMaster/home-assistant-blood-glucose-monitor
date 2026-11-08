"""Device triggers of the Blood Glucose Monitor integration.

Notifications are automations: each enabled alarm offers two triggers on the
device of the person, "started or repeated" and "acknowledged or over". The
automation gets the alarm data as ``trigger.event.data`` (``title``,
``message``, ``tag``, ``ack_action``, ``glucose``, ...).
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.homeassistant.triggers import event as event_trigger
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType
import probatio as vol

from .const import (
    ALARMS,
    CONF_REPORT,
    CONF_REPORT_ENTITY,
    DOMAIN,
    EVENT_ALARM,
    TRIGGER_ALERT,
    TRIGGER_ENDED,
    TRIGGER_REPORT,
)
from .monitor import enabled_alarms

TRIGGER_TYPES = [
    *(f"{alarm}_{kind}" for alarm in ALARMS for kind in (TRIGGER_ALERT, TRIGGER_ENDED)),
    TRIGGER_REPORT,
]

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES)}
)


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, Any]]:
    """List the triggers of the enabled alarms of a person."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return []
    alarms: set[str] = set()
    report = False
    for entry_id in device.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is not None and entry.domain == DOMAIN:
            alarms.update(enabled_alarms(entry.options))
            report |= bool(entry.options.get(CONF_REPORT, {}).get(CONF_REPORT_ENTITY))
    types = [
        f"{alarm}_{kind}"
        for alarm in ALARMS
        if alarm in alarms
        for kind in (TRIGGER_ALERT, TRIGGER_ENDED)
    ]
    if report:
        types.append(TRIGGER_REPORT)
    return [
        {
            CONF_PLATFORM: "device",
            CONF_DEVICE_ID: device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: trigger_type,
        }
        for trigger_type in types
    ]


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Listen to the alarm events of the device."""
    event_config = event_trigger.TRIGGER_SCHEMA(
        {
            event_trigger.CONF_PLATFORM: "event",
            event_trigger.CONF_EVENT_TYPE: EVENT_ALARM,
            event_trigger.CONF_EVENT_DATA: {
                CONF_DEVICE_ID: config[CONF_DEVICE_ID],
                CONF_TYPE: config[CONF_TYPE],
            },
        }
    )
    return await event_trigger.async_attach_trigger(
        hass, event_config, action, trigger_info, platform_type="device"
    )
