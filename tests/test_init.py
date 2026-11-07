"""Tests for setting up and unloading the integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.blood_glucose_monitor.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.blood_glucose_monitor.glucose import Trend

from .conftest import GLUCOSE_ENTITY, nightscout_attributes


@pytest.mark.usefixtures("glucose_state")
async def test_setup_and_unload(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """The entry sets up, follows the glucose sensor and unloads cleanly."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED

    source = config_entry.runtime_data
    assert source.reading.value == 112
    assert source.reading.trend is Trend.FALLING_SLIGHTLY

    hass.states.async_set(
        GLUCOSE_ENTITY, "65", nightscout_attributes(direction="SingleDown")
    )
    await hass.async_block_till_done()
    assert source.reading.value == 65
    assert source.reading.trend is Trend.FALLING

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.NOT_LOADED

    hass.states.async_set(GLUCOSE_ENTITY, "200", nightscout_attributes())
    await hass.async_block_till_done()
    assert source.reading.value == 65


@pytest.mark.usefixtures("glucose_state")
async def test_diagnostics(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """Diagnostics show the options, the parsed reading and the source states."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)
    assert diagnostics["options"] == {"glucose_entity": GLUCOSE_ENTITY}
    assert diagnostics["reading"] == {
        "value_mg_dl": 112,
        "trend": "falling_slightly",
        "trend_arrow": "↘",
        "change_mg_dl": -4,
        "reading_time": "2026-11-07T14:00:00+00:00",
        "reading_time_source": "attribute",
        "age_seconds": diagnostics["reading"]["age_seconds"],
    }
    assert diagnostics["source_states"][GLUCOSE_ENTITY]["state"] == "112"
