"""Tests for the config and options flow."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult, FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er
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
    SOURCE_PLATFORM,
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


async def open_sources_options(hass: HomeAssistant, entry_id: str) -> FlowResult:
    """Open the options and choose the glucose data step."""
    result = await hass.config_entries.options.async_init(entry_id)
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "sources"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "sources"
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

    result = await open_sources_options(hass, entry.entry_id)
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
    assert entry.runtime_data.source.entities.change == CHANGE_ENTITY


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

    result = await open_sources_options(hass, other.entry_id)
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

    result = await open_sources_options(hass, other.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY, CONF_TREND_ENTITY: TREND_ENTITY},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def open_options_step(
    hass: HomeAssistant, entry: MockConfigEntry, step: str
) -> FlowResult:
    """Open the options and choose a step of the menu."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": step}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == step
    return result


LOW_INPUT = {
    "threshold_entity": "input_number.low",
    "clear_offset": 10,
    "delay": 5,
    "repeat": 5,
    "snooze": 15,
    "only_when_home": False,
}


async def test_alarm_options_suggest_threshold(
    hass: HomeAssistant, source_entities: MockConfigEntry
) -> None:
    """The alarm step suggests the threshold sensor and the defaults."""
    hass.states.async_set(GLUCOSE_ENTITY, "112", nightscout_attributes())
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "sensor",
        SOURCE_PLATFORM,
        "target_range_bottom",
        suggested_object_id="test_target_range_bottom",
        config_entry=source_entities,
        translation_key="target_range_bottom",
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Alex",
        data={CONF_NAME: "Alex"},
        options={CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY},
    )
    entry.add_to_hass(hass)
    result = await open_options_step(hass, entry, "low")
    assert suggested_values(result) == {
        "threshold_entity": "sensor.test_target_range_bottom",
        "clear_offset": 10,
        "delay": 5,
        "repeat": 5,
        "snooze": 15,
    }
    assert result["description_placeholders"] == {"unit": "mg/dL"}

    result = await open_options_step(hass, entry, "urgent_low")
    assert "threshold_entity" not in suggested_values(result)

    # Saved without threshold (alarm off): no suggestion any more.
    result = await open_options_step(hass, entry, "low")
    user_input = dict(LOW_INPUT)
    del user_input["threshold_entity"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    result = await open_options_step(hass, entry, "low")
    assert "threshold_entity" not in suggested_values(result)


@pytest.mark.usefixtures("glucose_state")
async def test_alarm_options_saved(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Saving an alarm keeps the other options."""
    hass.states.async_set("input_number.low", "70", {"unit_of_measurement": "mg/dL"})
    result = await open_options_step(hass, config_entry, "low")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], LOW_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert dict(config_entry.options) == {
        CONF_GLUCOSE_ENTITY: GLUCOSE_ENTITY,
        "low": LOW_INPUT,
    }

    # Opening the step again shows the saved values.
    result = await open_options_step(hass, config_entry, "low")
    assert suggested_values(result)["threshold_entity"] == "input_number.low"


@pytest.mark.parametrize(
    ("user_input", "threshold_state", "errors"),
    [
        (LOW_INPUT, ("70", {}), {"threshold_entity": "threshold_unit_required"}),
        (
            LOW_INPUT,
            ("70", {"unit_of_measurement": "%"}),
            {"threshold_entity": "unsupported_unit"},
        ),
        (
            {**LOW_INPUT, "only_when_home": True},
            ("70", {"unit_of_measurement": "mg/dL"}),
            {"only_when_home": "person_required"},
        ),
    ],
)
@pytest.mark.usefixtures("glucose_state")
async def test_alarm_options_errors(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    user_input: dict[str, Any],
    threshold_state: tuple[str, dict[str, Any]] | None,
    errors: dict[str, str],
) -> None:
    """Invalid alarm settings are reported."""
    if threshold_state is not None:
        hass.states.async_set("input_number.low", *threshold_state)
    result = await open_options_step(hass, config_entry, "low")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {key: value for key, value in user_input.items() if value is not None},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == errors


@pytest.mark.usefixtures("glucose_state")
async def test_alarm_without_threshold_is_off(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """An alarm saved without threshold is off and gets no new suggestion."""
    result = await open_options_step(hass, config_entry, "urgent_low")
    user_input = dict(LOW_INPUT)
    del user_input["threshold_entity"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert config_entry.options["urgent_low"] == user_input


@pytest.mark.usefixtures("glucose_state")
async def test_data_loss_and_pause_options(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """The data loss alarm and the pause are saved."""
    result = await open_options_step(hass, config_entry, "data_loss")
    assert suggested_values(result) == {"max_age": 20, "repeat": 15, "snooze": 30}
    data_loss = {
        "max_age": 15,
        "repeat": 0,
        "snooze": 30,
        "only_when_home": False,
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], data_loss
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    result = await open_options_step(hass, config_entry, "pause")
    assert suggested_values(result) == {"duration": 60}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"duration": 30}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert config_entry.options["data_loss"] == data_loss
    assert config_entry.options["pause"] == {"duration": 30}


RAPID_INPUT = {
    "detection": "rate",
    "trend_level": "quickly",
    "delay": 0,
    "repeat": 0,
    "snooze": 30,
    "only_when_home": False,
}


@pytest.mark.parametrize(
    ("user_input", "rate_state", "errors"),
    [
        (RAPID_INPUT, None, {"rate_limit": "rate_limit_required"}),
        (
            {**RAPID_INPUT, "rate_entity": "input_number.rate"},
            ("x", {"unit_of_measurement": "mg/dL/min"}),
            {"rate_entity": "not_numeric"},
        ),
        (
            {**RAPID_INPUT, "rate_entity": "input_number.rate"},
            ("3", {"unit_of_measurement": "mg/dL"}),
            {"rate_entity": "rate_unit_required"},
        ),
        (
            {**RAPID_INPUT, "rate_entity": "input_number.rate"},
            ("3", {"unit_of_measurement": "mg/dL/min"}),
            {},
        ),
        ({**RAPID_INPUT, "rate_limit": 3}, None, {}),
        ({**RAPID_INPUT, "detection": "trend"}, None, {}),
    ],
)
@pytest.mark.usefixtures("glucose_state")
async def test_rapid_options(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    user_input: dict[str, Any],
    rate_state: tuple[str, dict[str, Any]] | None,
    errors: dict[str, str],
) -> None:
    """The rate limit of a rapid change alarm is checked."""
    if rate_state is not None:
        hass.states.async_set("input_number.rate", *rate_state)
    result = await open_options_step(hass, config_entry, "rapid_fall")
    assert suggested_values(result)["rate_limit"] == 3
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input
    )
    if errors:
        assert result["errors"] == errors
    else:
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()
        assert config_entry.options["rapid_fall"] == user_input


@pytest.mark.parametrize("step", ["high", "urgent_high", "rapid_rise"])
@pytest.mark.usefixtures("glucose_state")
async def test_new_alarm_steps_open(
    hass: HomeAssistant, config_entry: MockConfigEntry, step: str
) -> None:
    """The phase 3 alarm steps show their defaults."""
    result = await open_options_step(hass, config_entry, step)
    assert suggested_values(result)["snooze"] in (30, 60, 120)


CHARGING_INPUT = {
    "reminder_time": "20:00:00",
    "battery_limit": 75,
    "repeat": 0,
    "snooze": 30,
    "only_when_home": False,
}


async def test_charging_suggests_phone_sensors(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Battery and charging sensors are suggested from the person's phone."""
    hass.states.async_set(GLUCOSE_ENTITY, "112", nightscout_attributes())
    phone_entry = MockConfigEntry(domain="mobile_app", title="Phone")
    phone_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=phone_entry.entry_id, identifiers={("mobile_app", "phone")}
    )
    registry = er.async_get(hass)
    for domain, object_id, device_class in (
        ("device_tracker", "phone", None),
        ("sensor", "phone_battery_level", "battery"),
        ("sensor", "phone_battery_state", None),
        ("binary_sensor", "phone_is_charging", None),
    ):
        registry.async_get_or_create(
            domain,
            "mobile_app",
            object_id,
            suggested_object_id=object_id,
            config_entry=phone_entry,
            device_id=device.id,
            original_device_class=device_class,
        )
    hass.states.async_set(
        "person.alex", "home", {"device_trackers": ["device_tracker.phone"]}
    )
    hass.config_entries.async_update_entry(
        config_entry,
        options={**config_entry.options, CONF_PERSON_ENTITY: "person.alex"},
    )
    result = await open_options_step(hass, config_entry, "charging")
    suggested = suggested_values(result)
    assert suggested["battery_entity"] == "sensor.phone_battery_level"
    assert suggested["charging_entity"] == "binary_sensor.phone_is_charging"
    assert suggested["reminder_time"] == "20:00:00"


@pytest.mark.parametrize(
    ("user_input", "states", "errors"),
    [
        (CHARGING_INPUT, {}, {}),
        (
            {**CHARGING_INPUT, "battery_entity": "sensor.battery"},
            {},
            {"charging_entity": "charging_entities_required"},
        ),
        (
            {
                **CHARGING_INPUT,
                "battery_entity": "sensor.battery",
                "charging_entity": "sensor.state",
                "time_entity": "input_datetime.time",
                "battery_limit_entity": "input_number.limit",
            },
            {
                "sensor.battery": "full",
                "sensor.state": "sideways",
                "input_datetime.time": "evening",
                "input_number.limit": "many",
            },
            {
                "battery_entity": "not_numeric",
                "charging_entity": "unknown_charging_state",
                "time_entity": "invalid_time",
                "battery_limit_entity": "not_numeric",
            },
        ),
        (
            {
                **CHARGING_INPUT,
                "battery_entity": "sensor.battery",
                "charging_entity": "sensor.state",
                "time_entity": "input_datetime.time",
            },
            {
                "sensor.battery": "50",
                "sensor.state": "Not Charging",
                "input_datetime.time": "21:15:00",
            },
            {},
        ),
    ],
)
@pytest.mark.usefixtures("glucose_state")
async def test_charging_options(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    user_input: dict[str, Any],
    states: dict[str, str],
    errors: dict[str, str],
) -> None:
    """The charging reminder settings are checked."""
    for entity_id, state in states.items():
        hass.states.async_set(entity_id, state)
    result = await open_options_step(hass, config_entry, "charging")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input
    )
    if errors:
        assert result["errors"] == errors
    else:
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()
        assert config_entry.options["charging"] == user_input


@pytest.mark.usefixtures("glucose_state")
async def test_report_options(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """The report entity has to be on or off."""
    hass.states.async_set("binary_sensor.mode", "school")
    hass.states.async_set("schedule.blocks", "off")
    result = await open_options_step(hass, config_entry, "report")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"report_entity": "binary_sensor.mode"}
    )
    assert result["errors"] == {"report_entity": "not_on_off"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"report_entity": "schedule.blocks"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert config_entry.options["report"] == {"report_entity": "schedule.blocks"}
