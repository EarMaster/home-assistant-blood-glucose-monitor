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
from homeassistant.util import dt as dt_util
import probatio as vol

from .const import (
    ALARMS,
    ATTR_ALARM,
    ATTR_CHANGE,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_TIME,
    CHANGE_ALARMS,
    DOMAIN,
    SERVICE_ACKNOWLEDGE,
    SERVICE_RECORD_CHANGE,
)
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
RECORD_CHANGE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_CHANGE): vol.In(CHANGE_ALARMS),
        vol.Optional(ATTR_TIME): cv.datetime,
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
    def async_loaded_entry(call: ServiceCall) -> BloodGlucoseMonitorConfigEntry:
        """Return the loaded entry of a service call."""
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
        return entry

    @callback
    def async_acknowledge(call: ServiceCall) -> None:
        """Acknowledge one or all alarms of an entry."""
        monitor = async_loaded_entry(call).runtime_data.monitor
        monitor.async_acknowledge(call.data.get(ATTR_ALARM))

    @callback
    def async_record_change(call: ServiceCall) -> None:
        """Record a change of the cannula, the sensor or the reservoir."""
        entry = async_loaded_entry(call)
        monitor = entry.runtime_data.monitor
        alarm = call.data[ATTR_CHANGE]
        placeholders = {"name": entry.title}
        if alarm not in monitor.alarms:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="change_not_enabled",
                translation_placeholders=placeholders,
            )
        if not monitor.records_changes(alarm):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="change_from_entity",
                translation_placeholders=placeholders,
            )
        when = call.data.get(ATTR_TIME)
        if when is not None:
            if when.tzinfo is None:
                when = when.replace(tzinfo=dt_util.get_default_time_zone())
            if when > dt_util.utcnow():
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="change_in_future",
                )
        monitor.async_record_change(alarm, when)

    hass.services.async_register(
        DOMAIN, SERVICE_ACKNOWLEDGE, async_acknowledge, schema=ACKNOWLEDGE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RECORD_CHANGE,
        async_record_change,
        schema=RECORD_CHANGE_SCHEMA,
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
