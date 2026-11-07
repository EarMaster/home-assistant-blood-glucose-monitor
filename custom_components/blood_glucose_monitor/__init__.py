"""The Blood Glucose Monitor integration.

Adds optional, configurable hints (low/high alarms, night report, reminders)
on top of the glucose data of another integration such as Nightscout.

This integration is NOT a medical device and does not replace the alarms of
a CGM, insulin pump or medical app.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
import probatio as vol

from .const import ALARMS, ATTR_ALARM, ATTR_CONFIG_ENTRY_ID, DOMAIN, SERVICE_ACKNOWLEDGE
from .monitor import AlarmMonitor
from .source import GlucoseSource, SourceEntities

PLATFORMS = [Platform.BUTTON, Platform.EVENT, Platform.SENSOR, Platform.SWITCH]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

ACKNOWLEDGE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_ALARM): vol.In(ALARMS),
    }
)


@dataclass(slots=True)
class BloodGlucoseMonitorData:
    """Runtime data of one monitored person."""

    source: GlucoseSource
    monitor: AlarmMonitor


type BloodGlucoseMonitorConfigEntry = ConfigEntry[BloodGlucoseMonitorData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the services."""

    @callback
    def async_acknowledge(call: ServiceCall) -> None:
        """Acknowledge one or all alarms of an entry."""
        entry_id = call.data[ATTR_CONFIG_ENTRY_ID]
        entry: BloodGlucoseMonitorConfigEntry | None = (
            hass.config_entries.async_get_entry(entry_id)
        )
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_found",
                translation_placeholders={"entry_id": entry_id},
            )
        if entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_loaded",
                translation_placeholders={"name": entry.title},
            )
        entry.runtime_data.monitor.async_acknowledge(call.data.get(ATTR_ALARM))

    hass.services.async_register(
        DOMAIN, SERVICE_ACKNOWLEDGE, async_acknowledge, schema=ACKNOWLEDGE_SCHEMA
    )
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: BloodGlucoseMonitorConfigEntry
) -> bool:
    """Set up one monitored person from a config entry."""
    source = GlucoseSource(hass, SourceEntities.from_options(entry.options))
    entry.async_on_unload(source.async_start())
    monitor = AlarmMonitor(hass, entry, source)
    entry.runtime_data = BloodGlucoseMonitorData(source, monitor)
    await monitor.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: BloodGlucoseMonitorConfigEntry
) -> bool:
    """Unload a config entry."""
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.monitor.async_stop()
    return unloaded


async def async_remove_entry(
    hass: HomeAssistant, entry: BloodGlucoseMonitorConfigEntry
) -> None:
    """Remove the stored alarm states of a deleted entry."""
    await AlarmMonitor(
        hass, entry, GlucoseSource(hass, SourceEntities.from_options(entry.options))
    ).async_remove()
