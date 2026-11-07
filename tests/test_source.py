"""Tests for reading the source entities."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.blood_glucose_monitor.const import (
    CONF_CHANGE_ENTITY,
    CONF_GLUCOSE_ENTITY,
    CONF_GLUCOSE_UNIT,
    CONF_READING_TIME_ENTITY,
    CONF_TREND_ENTITY,
)
from custom_components.blood_glucose_monitor.glucose import ReadingTimeSource, Trend
from custom_components.blood_glucose_monitor.source import (
    GlucoseSource,
    SourceEntities,
    async_suggest_sources,
    build_reading,
    sensor_unit,
    to_mg_dl,
)

from .conftest import (
    CHANGE_ENTITY,
    GLUCOSE_ENTITY,
    READING_TIME_ENTITY,
    SOURCE_PLATFORM,
    TREND_ENTITY,
    nightscout_attributes,
)

ALL_SOURCES = SourceEntities(
    glucose=GLUCOSE_ENTITY,
    trend=TREND_ENTITY,
    change=CHANGE_ENTITY,
    reading_time=READING_TIME_ENTITY,
)
ATTRIBUTE_TIME = datetime(2026, 11, 7, 14, tzinfo=UTC)
ENTITY_TIME = datetime(2026, 11, 7, 14, 5, tzinfo=UTC)


def test_source_entities_from_options() -> None:
    """Empty optional entities are ignored."""
    sources = SourceEntities.from_options(
        {CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY, CONF_TREND_ENTITY: ""}
    )
    assert sources == SourceEntities(glucose=GLUCOSE_ENTITY)
    assert sources.entity_ids == [GLUCOSE_ENTITY]
    sources = SourceEntities.from_options(
        {
            CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY,
            CONF_TREND_ENTITY: TREND_ENTITY,
            CONF_CHANGE_ENTITY: CHANGE_ENTITY,
            CONF_READING_TIME_ENTITY: READING_TIME_ENTITY,
            CONF_GLUCOSE_UNIT: "mmol/L",
        }
    )
    assert sources.unit == "mmol/L"
    assert sources.entity_ids == [
        GLUCOSE_ENTITY,
        TREND_ENTITY,
        CHANGE_ENTITY,
        READING_TIME_ENTITY,
    ]


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        (112, "mg/dL", 112),
        (112, None, None),
        (5, "mmol/L", 90.08),
        (5, "°C", None),
        (None, "mg/dL", None),
    ],
)
def test_to_mg_dl(
    value: float | None, unit: str | None, expected: float | None
) -> None:
    """Values are converted to mg/dL, missing and unknown units are rejected."""
    result = to_mg_dl(value, unit)
    assert result == (None if expected is None else pytest.approx(expected))


async def test_reading_from_attributes(hass: HomeAssistant) -> None:
    """Without dedicated entities, the Nightscout attributes are used."""
    hass.states.async_set(GLUCOSE_ENTITY, "112", nightscout_attributes())
    reading = build_reading(hass, SourceEntities(glucose=GLUCOSE_ENTITY))
    assert reading.value == 112
    assert reading.trend is Trend.FALLING_SLIGHTLY
    assert reading.change == -4
    assert reading.reading_time == ATTRIBUTE_TIME
    assert reading.reading_time_source is ReadingTimeSource.ATTRIBUTE


async def test_reading_prefers_dedicated_entities(hass: HomeAssistant) -> None:
    """Dedicated entities win over attributes; mmol/L values are converted."""
    hass.states.async_set(GLUCOSE_ENTITY, "112", nightscout_attributes())
    hass.states.async_set(TREND_ENTITY, "rising")
    hass.states.async_set(CHANGE_ENTITY, "0.5", {"unit_of_measurement": "mmol/L"})
    hass.states.async_set(READING_TIME_ENTITY, ENTITY_TIME.isoformat())
    reading = build_reading(hass, ALL_SOURCES)
    assert reading.trend is Trend.RISING
    assert reading.change == pytest.approx(9.008)
    assert reading.reading_time == ENTITY_TIME
    assert reading.reading_time_source is ReadingTimeSource.ENTITY


async def test_reading_falls_back_when_entities_unavailable(
    hass: HomeAssistant,
) -> None:
    """Unavailable dedicated entities fall back to the attributes."""
    hass.states.async_set(GLUCOSE_ENTITY, "112", nightscout_attributes())
    for entity_id in (TREND_ENTITY, CHANGE_ENTITY, READING_TIME_ENTITY):
        hass.states.async_set(entity_id, "unavailable")
    reading = build_reading(hass, ALL_SOURCES)
    assert reading.trend is Trend.FALLING_SLIGHTLY
    assert reading.change == -4
    assert reading.reading_time_source is ReadingTimeSource.ATTRIBUTE


async def test_reading_without_time(hass: HomeAssistant) -> None:
    """Without time information, the reading time stays unknown."""
    hass.states.async_set(GLUCOSE_ENTITY, "6.2", {"unit_of_measurement": "mmol/L"})
    reading = build_reading(hass, SourceEntities(glucose=GLUCOSE_ENTITY))
    assert reading.value == pytest.approx(111.6992)
    assert reading.trend is None
    assert reading.change is None
    assert reading.reading_time is None
    assert reading.reading_time_source is None


async def test_reading_without_unit(hass: HomeAssistant) -> None:
    """Sensors without a unit are only read with the unit set in the entry."""
    hass.states.async_set(GLUCOSE_ENTITY, "6.2", {"delta": -0.3})
    hass.states.async_set(CHANGE_ENTITY, "0.5")
    sources = SourceEntities(glucose=GLUCOSE_ENTITY, change=CHANGE_ENTITY)
    reading = build_reading(hass, sources)
    assert reading.value is None
    assert reading.change is None

    reading = build_reading(
        hass,
        SourceEntities(glucose=GLUCOSE_ENTITY, change=CHANGE_ENTITY, unit="mmol/L"),
    )
    assert reading.value == pytest.approx(111.6992)
    assert reading.change == pytest.approx(9.008)

    # The delta attribute has the unit of the glucose sensor.
    reading = build_reading(hass, SourceEntities(glucose=GLUCOSE_ENTITY, unit="mmol/L"))
    assert reading.change == pytest.approx(-5.4048)


async def test_reported_unit_wins(hass: HomeAssistant) -> None:
    """The unit set in the entry only applies to sensors without a unit."""
    hass.states.async_set(GLUCOSE_ENTITY, "112", {"unit_of_measurement": "mg/dL"})
    reading = build_reading(hass, SourceEntities(glucose=GLUCOSE_ENTITY, unit="mmol/L"))
    assert reading.value == 112


async def test_unit_from_entity_registry(hass: HomeAssistant) -> None:
    """The unit of the entity registry is used when the state has none."""
    registry = er.async_get(hass)
    entry = registry.async_get_or_create(
        "sensor", SOURCE_PLATFORM, "registry_unit", unit_of_measurement="mmol/L"
    )
    assert sensor_unit(hass, entry.entity_id) == "mmol/L"
    hass.states.async_set(entry.entity_id, "6.2")
    assert sensor_unit(hass, entry.entity_id) == "mmol/L"
    assert sensor_unit(hass, "sensor.not_registered") is None


@pytest.mark.parametrize("state", ["unavailable", "unknown"])
async def test_reading_without_value(hass: HomeAssistant, state: str) -> None:
    """An unavailable glucose sensor gives an empty reading."""
    hass.states.async_set(GLUCOSE_ENTITY, state)
    reading = build_reading(hass, SourceEntities(glucose=GLUCOSE_ENTITY))
    assert reading.value is None
    assert reading.reading_time is None


async def test_missing_glucose_entity(hass: HomeAssistant) -> None:
    """A glucose entity that does not exist gives an empty reading."""
    reading = build_reading(hass, SourceEntities(glucose=GLUCOSE_ENTITY))
    assert reading.value is None


async def test_glucose_source_notifies_on_change(hass: HomeAssistant) -> None:
    """Listeners are called when, and only when, the reading changes."""
    hass.states.async_set(GLUCOSE_ENTITY, "112", nightscout_attributes())
    source = GlucoseSource(hass, ALL_SOURCES)
    stop = source.async_start()
    calls: list[float | None] = []
    remove = source.async_add_listener(lambda: calls.append(source.reading.value))

    hass.states.async_set(GLUCOSE_ENTITY, "108", nightscout_attributes())
    await hass.async_block_till_done()
    assert calls == [108]

    # Unrelated attribute change, same reading: no call
    hass.states.async_set(
        GLUCOSE_ENTITY, "108", nightscout_attributes(device="xDrip-UiBased")
    )
    await hass.async_block_till_done()
    assert calls == [108]

    hass.states.async_set(TREND_ENTITY, "falling")
    await hass.async_block_till_done()
    assert source.reading.trend is Trend.FALLING
    assert len(calls) == 2

    remove()
    hass.states.async_set(GLUCOSE_ENTITY, "100", nightscout_attributes())
    await hass.async_block_till_done()
    assert len(calls) == 2
    assert source.reading.value == 100

    stop()
    hass.states.async_set(GLUCOSE_ENTITY, "90", nightscout_attributes())
    await hass.async_block_till_done()
    assert source.reading.value == 100


async def test_suggest_sources_by_config_entry(
    hass: HomeAssistant, source_entities: MockConfigEntry
) -> None:
    """Sensors of the same config entry are suggested by translation key."""
    assert async_suggest_sources(hass, GLUCOSE_ENTITY) == {
        CONF_TREND_ENTITY: TREND_ENTITY,
        CONF_CHANGE_ENTITY: CHANGE_ENTITY,
        CONF_READING_TIME_ENTITY: READING_TIME_ENTITY,
    }


async def test_suggest_sources_by_device(hass: HomeAssistant) -> None:
    """Sensors of the same device are suggested, disabled ones are skipped."""
    dexcom_entry = MockConfigEntry(domain="dexcom", title="Dexcom")
    dexcom_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=dexcom_entry.entry_id, identifiers={("dexcom", "user")}
    )
    registry = er.async_get(hass)
    common = {"config_entry": dexcom_entry, "device_id": device.id}
    glucose = registry.async_get_or_create(
        "sensor", "dexcom", "value", suggested_object_id="dexcom_glucose", **common
    )
    registry.async_get_or_create(
        "sensor",
        "dexcom",
        "trend",
        suggested_object_id="dexcom_trend",
        translation_key="glucose_trend",
        **common,
    )
    registry.async_get_or_create(
        "sensor",
        "dexcom",
        "reading_time",
        suggested_object_id="dexcom_reading_time",
        translation_key="glucose_reading_time",
        disabled_by=er.RegistryEntryDisabler.USER,
        **common,
    )
    registry.async_get_or_create(
        "binary_sensor",
        "dexcom",
        "other",
        suggested_object_id="dexcom_other",
        translation_key="glucose_change",
        **common,
    )

    assert async_suggest_sources(hass, glucose.entity_id) == {
        CONF_TREND_ENTITY: "sensor.dexcom_trend"
    }


async def test_suggest_sources_unknown_entity(hass: HomeAssistant) -> None:
    """Entities without registry entry get no suggestions."""
    assert async_suggest_sources(hass, "sensor.not_registered") == {}
    registry = er.async_get(hass)
    lonely = registry.async_get_or_create("sensor", SOURCE_PLATFORM, "lonely")
    assert async_suggest_sources(hass, lonely.entity_id) == {}
