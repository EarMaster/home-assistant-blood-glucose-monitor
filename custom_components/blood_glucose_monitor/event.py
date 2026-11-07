"""Alarm event entity of the Blood Glucose Monitor integration.

Every alarm notification (triggered, repeat, acknowledged, resolved) is an
event, so the alarms show up in the logbook and can trigger automations.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BloodGlucoseMonitorConfigEntry
from .alarm import Phase
from .entity import BloodGlucoseMonitorEntity

PARALLEL_UPDATES = 0

# Variables of the user's actions that are also event attributes.
EVENT_ATTRIBUTES = (
    "alarm",
    "phase",
    "glucose",
    "unit",
    "trend",
    "delta",
    "rate",
    "data_age_min",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BloodGlucoseMonitorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the alarm event entity (the data loss alarm is always active)."""
    async_add_entities([AlarmEventEntity(entry)])


class AlarmEventEntity(BloodGlucoseMonitorEntity, EventEntity):
    """Events of all alarms of one person."""

    _attr_translation_key = "alarm"

    def __init__(self, entry: BloodGlucoseMonitorConfigEntry) -> None:
        """Initialize."""
        super().__init__(entry, "alarm")
        self._attr_event_types = [
            f"{alarm}_{phase.value}" for alarm in self.monitor.alarms for phase in Phase
        ]

    async def async_added_to_hass(self) -> None:
        """Listen to alarm events instead of state updates."""
        self.async_on_remove(self.monitor.async_add_event_listener(self._async_event))

    @callback
    def _async_event(self, alarm: str, phase: Phase, variables: dict[str, Any]) -> None:
        """Record an alarm event."""
        self._trigger_event(
            f"{alarm}_{phase.value}",
            {key: variables[key] for key in EVENT_ATTRIBUTES},
        )
        self.async_write_ha_state()
