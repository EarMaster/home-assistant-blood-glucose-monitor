"""Links to the automation builder of the documentation site.

The link carries the name of the person and the entity IDs of the event
entities, so the builder only offers what is set up and fills in the right
entities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlencode

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import BUILDER_URL, CONF_REPORT, DOMAIN
from .monitor import warning_alarms

if TYPE_CHECKING:
    from . import BloodGlucoseMonitorConfigEntry


@callback
def builder_url(hass: HomeAssistant, entry: BloodGlucoseMonitorConfigEntry) -> str:
    """Return the link to the automation builder for one person."""
    registry = er.async_get(hass)
    params: dict[str, str] = {"name": entry.title}
    for key in (*entry.runtime_data.monitor.alarms, CONF_REPORT):
        entity_key = key if key == CONF_REPORT else f"{key}_alarm"
        unique_id = f"{entry.entry_id}_{entity_key}_event"
        if entity_id := registry.async_get_entity_id("event", DOMAIN, unique_id):
            params[key] = entity_id
    if warnings := [
        alarm for alarm in warning_alarms(entry.options) if alarm in params
    ]:
        params["soon"] = ",".join(warnings)
    return f"{BUILDER_URL}?{urlencode(params)}"


@callback
def async_update_device_link(
    hass: HomeAssistant, entry: BloodGlucoseMonitorConfigEntry
) -> None:
    """Link the device page of the person to the automation builder."""
    registry = dr.async_get(hass)
    device = registry.async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    )
    if device is not None:
        registry.async_update_device(
            device.id, configuration_url=builder_url(hass, entry)
        )
