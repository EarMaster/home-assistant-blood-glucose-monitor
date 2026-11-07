"""Read glucose data from the configured source entities.

The glucose data itself (value, trend, change, reading time, thresholds) is
provided by the integration that connects to the CGM, e.g. Nightscout,
Dexcom or any other source. This module only reads those entities. When no
dedicated entity is configured for trend, change or reading time, the matching
state attributes of the glucose sensor are used instead (Nightscout exposes
``direction``, ``delta`` and ``date``).

Nothing is guessed: sensors without a unit need the unit set in the entry,
and without a reading time the reading has none.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfBloodGlucoseConcentration,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util.unit_conversion import BloodGlucoseConcentrationConverter

from .const import (
    ATTR_SOURCE_DATE,
    ATTR_SOURCE_DELTA,
    ATTR_SOURCE_DIRECTION,
    CONF_CHANGE_ENTITY,
    CONF_GLUCOSE_ENTITY,
    CONF_GLUCOSE_UNIT,
    CONF_READING_TIME_ENTITY,
    CONF_TREND_ENTITY,
    SOURCE_TRANSLATION_KEY_CHANGE,
    SOURCE_TRANSLATION_KEY_READING_TIME,
    SOURCE_TRANSLATION_KEY_TREND,
)
from .glucose import (
    GlucoseReading,
    ReadingTimeSource,
    parse_number,
    parse_timestamp,
    parse_trend,
)

_LOGGER = logging.getLogger(__name__)

MG_DL = UnitOfBloodGlucoseConcentration.MILLIGRAMS_PER_DECILITER

_SUGGESTION_KEYS: dict[str, str] = {
    SOURCE_TRANSLATION_KEY_TREND: CONF_TREND_ENTITY,
    SOURCE_TRANSLATION_KEY_CHANGE: CONF_CHANGE_ENTITY,
    SOURCE_TRANSLATION_KEY_READING_TIME: CONF_READING_TIME_ENTITY,
}


@dataclass(frozen=True, slots=True)
class SourceEntities:
    """Entity IDs the glucose data is read from."""

    glucose: str
    trend: str | None = None
    change: str | None = None
    reading_time: str | None = None
    unit: str | None = None
    """Unit of glucose and change sensors that do not report one."""

    @classmethod
    def from_options(cls, options: Mapping[str, Any]) -> SourceEntities:
        """Create from config entry options."""
        return cls(
            glucose=options[CONF_GLUCOSE_ENTITY],
            trend=options.get(CONF_TREND_ENTITY) or None,
            change=options.get(CONF_CHANGE_ENTITY) or None,
            reading_time=options.get(CONF_READING_TIME_ENTITY) or None,
            unit=options.get(CONF_GLUCOSE_UNIT) or None,
        )

    @property
    def entity_ids(self) -> list[str]:
        """Return all configured entity IDs."""
        return [
            entity_id
            for entity_id in (self.glucose, self.trend, self.change, self.reading_time)
            if entity_id
        ]


def to_mg_dl(value: float | None, unit: str | None) -> float | None:
    """Convert a glucose value to mg/dL.

    Values without a unit or with an unknown unit are rejected.
    """
    if value is None or unit not in BloodGlucoseConcentrationConverter.VALID_UNITS:
        return None
    if unit == MG_DL:
        return value
    return BloodGlucoseConcentrationConverter.convert(value, unit, MG_DL)


def state_value(state: State | None) -> str | None:
    """Return the state value, ``None`` if missing, unknown or unavailable."""
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None
    return state.state


def sensor_unit(hass: HomeAssistant, entity_id: str) -> str | None:
    """Return the unit a sensor reports, from its state or entity registry."""
    if (state := hass.states.get(entity_id)) is not None and (
        unit := state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
    ):
        return str(unit)
    if (entry := er.async_get(hass).async_get(entity_id)) is not None:
        return entry.unit_of_measurement
    return None


def _value_mg_dl(hass: HomeAssistant, entity_id: str, unit: str | None) -> float | None:
    """Return the numeric state of a sensor in mg/dL.

    ``unit`` is used when the sensor does not report a unit itself.
    """
    return to_mg_dl(
        parse_number(state_value(hass.states.get(entity_id))),
        sensor_unit(hass, entity_id) or unit,
    )


def build_reading(hass: HomeAssistant, sources: SourceEntities) -> GlucoseReading:
    """Build a reading from the current states of the source entities."""
    glucose_state = hass.states.get(sources.glucose)
    attributes: Mapping[str, Any] = (
        glucose_state.attributes if glucose_state is not None else {}
    )
    glucose_unit = sensor_unit(hass, sources.glucose) or sources.unit
    value = _value_mg_dl(hass, sources.glucose, sources.unit)

    trend = None
    if sources.trend:
        trend = parse_trend(state_value(hass.states.get(sources.trend)))
    if trend is None:
        trend = parse_trend(attributes.get(ATTR_SOURCE_DIRECTION))

    change = None
    if sources.change:
        change = _value_mg_dl(hass, sources.change, sources.unit)
    if change is None:
        # The delta attribute has the unit of the glucose sensor (Nightscout).
        change = to_mg_dl(parse_number(attributes.get(ATTR_SOURCE_DELTA)), glucose_unit)

    # The reading time is never guessed, see GlucoseReading.reading_time.
    reading_time = None
    reading_time_source = None
    if sources.reading_time and (
        reading_time := parse_timestamp(
            state_value(hass.states.get(sources.reading_time))
        )
    ):
        reading_time_source = ReadingTimeSource.ENTITY
    elif reading_time := parse_timestamp(attributes.get(ATTR_SOURCE_DATE)):
        reading_time_source = ReadingTimeSource.ATTRIBUTE

    return GlucoseReading(
        value=value,
        trend=trend,
        change=change,
        reading_time=reading_time,
        reading_time_source=reading_time_source,
    )


class GlucoseSource:
    """Keep the latest glucose reading of one person up to date."""

    def __init__(self, hass: HomeAssistant, entities: SourceEntities) -> None:
        """Initialize."""
        self.hass = hass
        self.entities = entities
        self._reading = build_reading(hass, entities)
        self._listeners: list[Callable[[], None]] = []

    @property
    def reading(self) -> GlucoseReading:
        """Return the latest reading."""
        return self._reading

    @callback
    def async_start(self) -> CALLBACK_TYPE:
        """Start tracking the source entities, return a function to stop."""
        self._reading = build_reading(self.hass, self.entities)
        return async_track_state_change_event(
            self.hass, self.entities.entity_ids, self._async_source_changed
        )

    @callback
    def async_add_listener(self, update_callback: Callable[[], None]) -> CALLBACK_TYPE:
        """Call ``update_callback`` when the reading changes."""
        self._listeners.append(update_callback)

        @callback
        def remove_listener() -> None:
            self._listeners.remove(update_callback)

        return remove_listener

    @callback
    def _async_source_changed(self, event: Event[EventStateChangedData]) -> None:
        """Rebuild the reading when a source entity changes."""
        reading = build_reading(self.hass, self.entities)
        if reading == self._reading:
            return
        self._reading = reading
        _LOGGER.debug("New reading for %s: %s", self.entities.glucose, reading)
        for update_callback in list(self._listeners):
            update_callback()


@callback
def async_suggest_sources(
    hass: HomeAssistant, glucose_entity_id: str
) -> dict[str, str]:
    """Suggest trend, change and reading time entities for a glucose sensor.

    Looks at the sensors of the same device and config entry as the glucose
    sensor and matches them by their translation key (as used by Dexcom and
    Nightscout).
    """
    registry = er.async_get(hass)
    glucose_entry = registry.async_get(glucose_entity_id)
    if glucose_entry is None:
        return {}

    candidates: dict[str, er.RegistryEntry] = {}
    if glucose_entry.config_entry_id:
        candidates.update(
            (entry.entity_id, entry)
            for entry in er.async_entries_for_config_entry(
                registry, glucose_entry.config_entry_id
            )
        )
    if glucose_entry.device_id:
        candidates.update(
            (entry.entity_id, entry)
            for entry in er.async_entries_for_device(registry, glucose_entry.device_id)
        )

    suggestions: dict[str, str] = {}
    for entity_id in sorted(candidates):
        entry = candidates[entity_id]
        if (
            entity_id == glucose_entity_id
            or entry.domain != "sensor"
            or entry.disabled_by is not None
            or (option := _SUGGESTION_KEYS.get(entry.translation_key or "")) is None
        ):
            continue
        suggestions.setdefault(option, entity_id)
    return suggestions
