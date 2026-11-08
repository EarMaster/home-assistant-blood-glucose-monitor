"""Event entities of the Blood Glucose Monitor integration.

Notifications are automations on these entities ("Event received"): every
enabled alarm has its own event entity with the event types "started or
repeated" (``{alarm}_alert``), "acknowledged or over" (``{alarm}_ended``) and,
for change reminders with a warning, "due soon" (``{alarm}_soon``). The
report has its own event entity with the event type ``report``. The data of
an event (``title``, ``message``, ``tag``, ``ack_action``, ``glucose``, ...)
are the attributes of the entity, in automations
``trigger.to_state.attributes``.

The event types are unique per person, so an automation can also target the
whole device and filter by event type.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BloodGlucoseMonitorConfigEntry
from .const import (
    CHANGE_ALARMS,
    TRIGGER_ALERT,
    TRIGGER_ENDED,
    TRIGGER_REPORT,
    TRIGGER_SOON,
)
from .entity import BloodGlucoseMonitorEntity
from .monitor import warning_alarms

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BloodGlucoseMonitorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add an event entity per enabled alarm and one for the report."""
    monitor = entry.runtime_data.monitor
    warnings = warning_alarms(entry.options)
    entities: list[MonitorEventEntity] = [
        MonitorEventEntity(
            entry,
            f"{alarm}_alarm",
            [
                f"{alarm}_{TRIGGER_ALERT}",
                f"{alarm}_{TRIGGER_ENDED}",
                *(
                    [f"{alarm}_{TRIGGER_SOON}"]
                    if alarm in CHANGE_ALARMS and alarm in warnings
                    else []
                ),
            ],
        )
        for alarm in monitor.alarms
    ]
    if monitor.report is not None:
        entities.append(MonitorEventEntity(entry, "report", [TRIGGER_REPORT]))
    async_add_entities(entities)


class MonitorEventEntity(BloodGlucoseMonitorEntity, EventEntity):
    """Events of one alarm or of the report of one person."""

    def __init__(
        self,
        entry: BloodGlucoseMonitorConfigEntry,
        key: str,
        event_types: list[str],
    ) -> None:
        """Initialize."""
        super().__init__(entry, f"{key}_event")
        self._attr_translation_key = key
        self._attr_event_types = event_types

    async def async_added_to_hass(self) -> None:
        """Listen to the events of the monitor instead of state updates."""
        self.async_on_remove(self.monitor.async_add_event_listener(self._async_event))

    @callback
    def _async_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Record an event of this entity."""
        if event_type in self.event_types:
            self._trigger_event(event_type, data)
            self.async_write_ha_state()
