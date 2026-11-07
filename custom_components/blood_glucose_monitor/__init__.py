"""The Blood Glucose Monitor integration.

Adds optional, configurable hints (low/high alarms, night report, reminders)
on top of the glucose data of another integration such as Nightscout.

This integration is NOT a medical device and does not replace the alarms of
a CGM, insulin pump or medical app.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .source import GlucoseSource, SourceEntities

type BloodGlucoseMonitorConfigEntry = ConfigEntry[GlucoseSource]


async def async_setup_entry(
    hass: HomeAssistant, entry: BloodGlucoseMonitorConfigEntry
) -> bool:
    """Set up one monitored person from a config entry."""
    source = GlucoseSource(hass, SourceEntities.from_options(entry.options))
    entry.async_on_unload(source.async_start())
    entry.runtime_data = source
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: BloodGlucoseMonitorConfigEntry
) -> bool:
    """Unload a config entry."""
    return True
