"""Pause switch of the Blood Glucose Monitor integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BloodGlucoseMonitorConfigEntry
from .const import PAUSABLE_ALARMS
from .entity import BloodGlucoseMonitorEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BloodGlucoseMonitorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the pause switch if a pausable alarm is enabled."""
    if any(alarm in PAUSABLE_ALARMS for alarm in entry.runtime_data.monitor.alarms):
        async_add_entities([PauseSwitch(entry)])


class PauseSwitch(BloodGlucoseMonitorEntity, SwitchEntity):
    """Pause the low and data loss alarms; turns off by itself."""

    _attr_translation_key = "pause"

    def __init__(self, entry: BloodGlucoseMonitorConfigEntry) -> None:
        """Initialize."""
        super().__init__(entry, "pause")

    @property
    def is_on(self) -> bool:
        """Return True while paused."""
        return self.monitor.paused

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return when the pause ends."""
        until = self.monitor.pause_until if self.monitor.paused else None
        return {"until": None if until is None else until.isoformat()}

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Pause the alarms."""
        self.monitor.async_pause(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Resume the alarms."""
        self.monitor.async_pause(False)
