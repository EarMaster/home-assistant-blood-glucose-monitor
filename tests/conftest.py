"""Fixtures for Blood Glucose Monitor tests.

All glucose values used in tests are synthetic.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.blood_glucose_monitor.const import (
    CONF_GLUCOSE_ENTITY,
    CONF_NAME,
    DOMAIN,
)

GLUCOSE_ENTITY = "sensor.test_glucose"
TREND_ENTITY = "sensor.test_glucose_trend"
CHANGE_ENTITY = "sensor.test_glucose_change"
READING_TIME_ENTITY = "sensor.test_glucose_reading_time"
SOURCE_PLATFORM = "nightscout"

READING_TIME = "2026-11-07T14:00:00+00:00"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading the custom integration in all tests."""


def nightscout_attributes(**overrides: Any) -> dict[str, Any]:
    """Return attributes like the Nightscout glucose sensor provides them."""
    return {
        "unit_of_measurement": "mg/dL",
        "device_class": "blood_glucose_concentration",
        "date": READING_TIME,
        "delta": -4,
        "direction": "FortyFiveDown",
        **overrides,
    }


@pytest.fixture
def glucose_state(hass: HomeAssistant) -> None:
    """Set a glucose state with Nightscout style attributes."""
    hass.states.async_set(GLUCOSE_ENTITY, "112", nightscout_attributes())


@pytest.fixture
def source_entities(hass: HomeAssistant) -> MockConfigEntry:
    """Register glucose, trend, change and reading time sensors of one source."""
    source_entry = MockConfigEntry(domain=SOURCE_PLATFORM, title="Nightscout")
    source_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    for object_id, translation_key, device_class in (
        ("test_glucose", None, "blood_glucose_concentration"),
        ("test_glucose_trend", "glucose_trend", "enum"),
        ("test_glucose_change", "glucose_change", "blood_glucose_concentration"),
        ("test_glucose_reading_time", "glucose_reading_time", "timestamp"),
    ):
        registry.async_get_or_create(
            "sensor",
            SOURCE_PLATFORM,
            object_id,
            suggested_object_id=object_id,
            config_entry=source_entry,
            translation_key=translation_key,
            original_device_class=device_class,
        )
    return source_entry


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return a config entry for one monitored person."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Alex",
        data={CONF_NAME: "Alex"},
        options={CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY},
    )
    entry.add_to_hass(hass)
    return entry
