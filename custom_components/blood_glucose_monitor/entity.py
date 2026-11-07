"""Base entity of the Blood Glucose Monitor integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from . import BloodGlucoseMonitorConfigEntry
from .const import DOMAIN
from .monitor import AlarmMonitor


class BloodGlucoseMonitorEntity(Entity):
    """An entity of one monitored person."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: BloodGlucoseMonitorConfigEntry, key: str) -> None:
        """Initialize."""
        self.monitor: AlarmMonitor = entry.runtime_data.monitor
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        """Follow the alarm monitor."""
        self.async_on_remove(self.monitor.async_add_listener(self.async_write_ha_state))
