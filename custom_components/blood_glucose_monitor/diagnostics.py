"""Diagnostics for the Blood Glucose Monitor integration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from . import BloodGlucoseMonitorConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BloodGlucoseMonitorConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    source = entry.runtime_data.source
    monitor = entry.runtime_data.monitor
    reading = source.reading
    age = reading.age(dt_util.utcnow())
    source_states: dict[str, Any] = {}
    for entity_id in source.entities.entity_ids:
        state = hass.states.get(entity_id)
        source_states[entity_id] = (
            None
            if state is None
            else {
                "state": state.state,
                "attributes": dict(state.attributes),
                "last_changed": state.last_changed.isoformat(),
            }
        )
    return {
        "options": dict(entry.options),
        "reading": {
            "value_mg_dl": reading.value,
            "trend": reading.trend,
            "trend_arrow": reading.trend_arrow,
            "change_mg_dl": reading.change,
            "reading_time": reading.reading_time.isoformat()
            if reading.reading_time
            else None,
            "reading_time_source": reading.reading_time_source,
            "age_seconds": None if age is None else round(age.total_seconds()),
        },
        "source_states": source_states,
        "alarms": {
            "last_reading_time": monitor.last_reading_time.isoformat()
            if monitor.last_reading_time
            else None,
            "paused": monitor.paused,
            "states": {
                alarm: engine.status.as_dict()
                for alarm, engine in monitor.engines.items()
            },
        },
    }
