"""Acknowledge buttons of the Blood Glucose Monitor integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BloodGlucoseMonitorConfigEntry
from .entity import BloodGlucoseMonitorEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BloodGlucoseMonitorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add one acknowledge button per enabled alarm."""
    async_add_entities(
        AcknowledgeButton(entry, alarm) for alarm in entry.runtime_data.monitor.alarms
    )


class AcknowledgeButton(BloodGlucoseMonitorEntity, ButtonEntity):
    """Acknowledge one alarm; other alarms are not affected."""

    def __init__(self, entry: BloodGlucoseMonitorConfigEntry, alarm: str) -> None:
        """Initialize."""
        super().__init__(entry, f"acknowledge_{alarm}")
        self.alarm = alarm
        self._attr_translation_key = f"acknowledge_{alarm}"

    async def async_added_to_hass(self) -> None:
        """Buttons have no state to follow."""

    async def async_press(self) -> None:
        """Acknowledge the alarm."""
        self.monitor.async_acknowledge(self.alarm)
