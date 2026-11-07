"""Tests for the config and options flow."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult, FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.blood_glucose_monitor.const import (
    CONF_CHANGE_ENTITY,
    CONF_DISCLAIMER_ACCEPTED,
    CONF_GLUCOSE_ENTITY,
    CONF_GLUCOSE_UNIT,
    CONF_NAME,
    CONF_PERSON_ENTITY,
    CONF_READING_TIME_ENTITY,
    CONF_TREND_ENTITY,
    DOMAIN,
)

from .conftest import (
    CHANGE_ENTITY,
    GLUCOSE_ENTITY,
    READING_TIME_ENTITY,
    TREND_ENTITY,
    nightscout_attributes,
)

OTHER_GLUCOSE_ENTITY = "sensor.other_glucose"


def suggested_values(result: FlowResult) -> dict[str, Any]:
    """Return the suggested values of a form."""
    return {
        str(key): key.description["suggested_value"]
        for key in result["data_schema"].schema
        if key.description and "suggested_value" in key.description
    }


async def start_flow_at_person_step(hass: HomeAssistant) -> FlowResult:
    """Start a flow and accept the disclaimer."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DISCLAIMER_ACCEPTED: True}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "person"
    return result


async def test_disclaimer_must_be_accepted(hass: HomeAssistant) -> None:
    """The flow cannot continue without accepting the disclaimer."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DISCLAIMER_ACCEPTED: False}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {CONF_DISCLAIMER_ACCEPTED: "disclaimer_required"}


@pytest.mark.usefixtures("source_entities", "glucose_state")
async def test_full_flow_with_suggestions(hass: HomeAssistant) -> None:
    """A complete flow suggests the source sensors and creates the entry."""
    result = await start_flow_at_person_step(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: " Alex ",
            CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY,
            CONF_PERSON_ENTITY: "person.alex",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "sources"
    assert result["description_placeholders"] == {"name": "Alex"}
    assert suggested_values(result) == {
        CONF_TREND_ENTITY: TREND_ENTITY,
        CONF_CHANGE_ENTITY: CHANGE_ENTITY,
        CONF_READING_TIME_ENTITY: READING_TIME_ENTITY,
    }

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TREND_ENTITY: TREND_ENTITY,
            CONF_READING_TIME_ENTITY: READING_TIME_ENTITY,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Alex"
    assert result["data"] == {CONF_NAME: "Alex"}
    assert result["options"] == {
        CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY,
        CONF_PERSON_ENTITY: "person.alex",
        CONF_TREND_ENTITY: TREND_ENTITY,
        CONF_READING_TIME_ENTITY: READING_TIME_ENTITY,
    }


@pytest.mark.usefixtures("glucose_state")
async def test_flow_without_suggestions(hass: HomeAssistant) -> None:
    """Without matching sensors, nothing is suggested and fields may stay empty."""
    result = await start_flow_at_person_step(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Sam", CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY}
    )
    assert result["step_id"] == "sources"
    assert suggested_values(result) == {}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY}


@pytest.mark.parametrize(
    ("user_input", "state", "errors"),
    [
        (
            {CONF_NAME: "   ", CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY},
            ("112", nightscout_attributes()),
            {CONF_NAME: "name_required"},
        ),
        (
            {CONF_NAME: "Alex", CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY},
            ("21", {"unit_of_measurement": "°C"}),
            {CONF_GLUCOSE_ENTITY: "unsupported_unit"},
        ),
        (
            {CONF_NAME: "Alex", CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY},
            ("high", {"unit_of_measurement": "mg/dL"}),
            {CONF_GLUCOSE_ENTITY: "not_numeric"},
        ),
    ],
)
async def test_person_step_errors(
    hass: HomeAssistant,
    user_input: dict[str, Any],
    state: tuple[str, dict[str, Any]],
    errors: dict[str, str],
) -> None:
    """Invalid input is reported on the person step."""
    hass.states.async_set(GLUCOSE_ENTITY, *state)
    result = await start_flow_at_person_step(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "person"
    assert result["errors"] == errors


async def test_glucose_sensor_without_unit(hass: HomeAssistant) -> None:
    """A glucose sensor without a unit needs the unit set in the sources step."""
    hass.states.async_set(GLUCOSE_ENTITY, "6.2")
    result = await start_flow_at_person_step(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Alex", CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY}
    )
    assert result["step_id"] == "sources"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_GLUCOSE_UNIT: "unit_required"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_GLUCOSE_UNIT: "mmol/L"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {
        CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY,
        CONF_GLUCOSE_UNIT: "mmol/L",
    }


@pytest.mark.parametrize(
    ("key", "entity_id", "state", "errors"),
    [
        (
            CONF_CHANGE_ENTITY,
            CHANGE_ENTITY,
            ("21", {"unit_of_measurement": "°C"}),
            {CONF_CHANGE_ENTITY: "unsupported_unit"},
        ),
        (
            CONF_CHANGE_ENTITY,
            CHANGE_ENTITY,
            ("up", {"unit_of_measurement": "mg/dL"}),
            {CONF_CHANGE_ENTITY: "not_numeric"},
        ),
        (
            CONF_CHANGE_ENTITY,
            CHANGE_ENTITY,
            ("-3", {}),
            {CONF_GLUCOSE_UNIT: "unit_required"},
        ),
        (
            CONF_TREND_ENTITY,
            TREND_ENTITY,
            ("sideways", {}),
            {CONF_TREND_ENTITY: "unknown_trend"},
        ),
        (
            CONF_READING_TIME_ENTITY,
            READING_TIME_ENTITY,
            ("a while ago", {}),
            {CONF_READING_TIME_ENTITY: "invalid_reading_time"},
        ),
    ],
)
@pytest.mark.usefixtures("glucose_state")
async def test_sources_step_errors(
    hass: HomeAssistant,
    key: str,
    entity_id: str,
    state: tuple[str, dict[str, Any]],
    errors: dict[str, str],
) -> None:
    """Sensors whose current value cannot be read are reported."""
    hass.states.async_set(entity_id, *state)
    result = await start_flow_at_person_step(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Alex", CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {key: entity_id}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "sources"
    assert result["errors"] == errors
    assert suggested_values(result) == {key: entity_id}


@pytest.mark.usefixtures("glucose_state")
async def test_sources_step_accepts_any_spelling(hass: HomeAssistant) -> None:
    """Sensors without device class are accepted when their values can be read."""
    hass.states.async_set(TREND_ENTITY, "Decreasing fast")
    hass.states.async_set(CHANGE_ENTITY, "-0.3")
    hass.states.async_set(READING_TIME_ENTITY, "1794060000000")
    result = await start_flow_at_person_step(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Alex", CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY}
    )
    user_input = {
        CONF_TREND_ENTITY: TREND_ENTITY,
        CONF_CHANGE_ENTITY: CHANGE_ENTITY,
        CONF_READING_TIME_ENTITY: READING_TIME_ENTITY,
        CONF_GLUCOSE_UNIT: "mmol/L",
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY, **user_input}


@pytest.mark.usefixtures("glucose_state")
async def test_glucose_sensor_already_monitored(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """A glucose sensor can be monitored by several entries after a notice."""
    result = await start_flow_at_person_step(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Alex 2", CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "already_monitored"
    assert result["description_placeholders"] == {
        "entity_id": GLUCOSE_ENTITY,
        "entries": config_entry.title,
    }

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "sources"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY}
    assert len(hass.config_entries.async_entries(DOMAIN)) == 2


@pytest.mark.usefixtures("glucose_state")
async def test_options_flow(hass: HomeAssistant) -> None:
    """The options flow replaces the source entities and keeps other options."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Alex",
        data={CONF_NAME: "Alex"},
        options={
            CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY,
            CONF_TREND_ENTITY: TREND_ENTITY,
            "other_option": 42,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    assert suggested_values(result) == {
        CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY,
        CONF_TREND_ENTITY: TREND_ENTITY,
    }

    # A change sensor without unit needs the unit.
    hass.states.async_set(CHANGE_ENTITY, "-3")
    user_input = {
        CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY,
        CONF_CHANGE_ENTITY: CHANGE_ENTITY,
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_GLUCOSE_UNIT: "unit_required"}

    hass.states.async_set(CHANGE_ENTITY, "-3", {"unit_of_measurement": "mg/dL"})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert dict(entry.options) == {
        CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY,
        CONF_CHANGE_ENTITY: CHANGE_ENTITY,
        "other_option": 42,
    }
    assert entry.runtime_data.entities.change == CHANGE_ENTITY


async def add_entry(hass: HomeAssistant, title: str, glucose: str) -> MockConfigEntry:
    """Add and set up another entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=title,
        data={CONF_NAME: title},
        options={CONF_GLUCOSE_ENTITY: glucose},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.usefixtures("glucose_state")
async def test_options_flow_already_monitored(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Switching to a sensor of another entry shows a notice before saving."""
    hass.states.async_set(OTHER_GLUCOSE_ENTITY, "120", nightscout_attributes())
    other = await add_entry(hass, "Sam", OTHER_GLUCOSE_ENTITY)

    result = await hass.config_entries.options.async_init(other.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "already_monitored"
    assert result["description_placeholders"] == {
        "entity_id": GLUCOSE_ENTITY,
        "entries": config_entry.title,
    }

    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert dict(other.options) == {CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY}
    assert dict(config_entry.options)[CONF_GLUCOSE_ENTITY] == GLUCOSE_ENTITY


@pytest.mark.usefixtures("glucose_state")
async def test_options_flow_shared_sensor_unchanged(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Saving without changing a shared sensor does not show the notice again."""
    other = await add_entry(hass, "Alex 2", GLUCOSE_ENTITY)

    result = await hass.config_entries.options.async_init(other.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY, CONF_TREND_ENTITY: TREND_ENTITY},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
