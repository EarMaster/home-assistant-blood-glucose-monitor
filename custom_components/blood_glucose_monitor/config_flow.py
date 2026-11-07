"""Config flow for the Blood Glucose Monitor integration."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import UnitOfBloodGlucoseConcentration
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)
from homeassistant.util.unit_conversion import BloodGlucoseConcentrationConverter
import probatio as vol

from .const import (
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
from .glucose import parse_number, parse_timestamp, parse_trend
from .source import async_suggest_sources, sensor_unit, state_value

# Any sensor can be selected: not every source sets a device class. The
# current values are checked instead.
SENSOR_SELECTOR = EntitySelector(EntitySelectorConfig(domain="sensor"))
PERSON_SELECTOR = EntitySelector(EntitySelectorConfig(domain="person"))
UNIT_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=[
            UnitOfBloodGlucoseConcentration.MILLIGRAMS_PER_DECILITER,
            UnitOfBloodGlucoseConcentration.MILLIMOLE_PER_LITER,
        ],
        mode=SelectSelectorMode.DROPDOWN,
    )
)

DISCLAIMER_SCHEMA = vol.Schema(
    {vol.Required(CONF_DISCLAIMER_ACCEPTED, default=False): BooleanSelector()}
)
PERSON_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): TextSelector(),
        vol.Required(CONF_GLUCOSE_ENTITY): SENSOR_SELECTOR,
        vol.Optional(CONF_PERSON_ENTITY): PERSON_SELECTOR,
    }
)
SOURCES_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_TREND_ENTITY): SENSOR_SELECTOR,
        vol.Optional(CONF_CHANGE_ENTITY): SENSOR_SELECTOR,
        vol.Optional(CONF_READING_TIME_ENTITY): SENSOR_SELECTOR,
        vol.Optional(CONF_GLUCOSE_UNIT): UNIT_SELECTOR,
    }
)
OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_GLUCOSE_ENTITY): SENSOR_SELECTOR,
        vol.Optional(CONF_PERSON_ENTITY): PERSON_SELECTOR,
    }
).extend(SOURCES_SCHEMA.schema)
# Notice without fields: submitting continues, closing the dialog cancels.
ALREADY_MONITORED_SCHEMA = vol.Schema({})

OPTION_KEYS = (
    CONF_GLUCOSE_ENTITY,
    CONF_PERSON_ENTITY,
    CONF_TREND_ENTITY,
    CONF_CHANGE_ENTITY,
    CONF_READING_TIME_ENTITY,
    CONF_GLUCOSE_UNIT,
)


def _clean_options(values: Mapping[str, Any]) -> dict[str, Any]:
    """Keep known option keys, drop empty values."""
    return {key: values[key] for key in OPTION_KEYS if values.get(key)}


def _unparsable(
    hass: HomeAssistant, entity_id: str, parse: Callable[[Any], object | None]
) -> bool:
    """Return True if the current state of a sensor cannot be parsed.

    Missing, unknown and unavailable states cannot be checked and pass.
    """
    value = state_value(hass.states.get(entity_id))
    return value is not None and parse(value) is None


def _validate_glucose_value(
    hass: HomeAssistant, key: str, entity_id: str
) -> dict[str, str]:
    """Return form errors for a sensor with a glucose value or change."""
    unit = sensor_unit(hass, entity_id)
    if unit is not None and unit not in BloodGlucoseConcentrationConverter.VALID_UNITS:
        return {key: "unsupported_unit"}
    if _unparsable(hass, entity_id, parse_number):
        return {key: "not_numeric"}
    return {}


def _validate_sources(hass: HomeAssistant, values: Mapping[str, Any]) -> dict[str, str]:
    """Return form errors for the optional source sensors and the unit."""
    errors: dict[str, str] = {}
    if change := values.get(CONF_CHANGE_ENTITY):
        errors |= _validate_glucose_value(hass, CONF_CHANGE_ENTITY, change)
    if (trend := values.get(CONF_TREND_ENTITY)) and _unparsable(
        hass, trend, parse_trend
    ):
        errors[CONF_TREND_ENTITY] = "unknown_trend"
    if (reading_time := values.get(CONF_READING_TIME_ENTITY)) and _unparsable(
        hass, reading_time, parse_timestamp
    ):
        errors[CONF_READING_TIME_ENTITY] = "invalid_reading_time"
    # The unit is never guessed: sensors without one need it set here.
    if not values.get(CONF_GLUCOSE_UNIT) and any(
        sensor_unit(hass, entity_id) is None
        for entity_id in (values[CONF_GLUCOSE_ENTITY], change)
        if entity_id
    ):
        errors[CONF_GLUCOSE_UNIT] = "unit_required"
    return errors


def _other_entries_monitoring(
    hass: HomeAssistant, entity_id: str, own_entry_id: str | None
) -> list[str]:
    """Return the titles of other entries that monitor the glucose sensor.

    Several entries may use the same sensor and work independently; the user
    only gets a notice.
    """
    return sorted(
        entry.title
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.entry_id != own_entry_id
        and entry.options.get(CONF_GLUCOSE_ENTITY) == entity_id
    )


def _already_monitored_placeholders(
    entity_id: str, titles: list[str]
) -> dict[str, str]:
    """Return the placeholders of the already monitored notice."""
    return {"entity_id": entity_id, "entries": ", ".join(titles)}


class BloodGlucoseMonitorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up one monitored person."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._name = ""
        self._options: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowHandler:
        """Return the options flow."""
        return OptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the disclaimer, which has to be accepted to continue."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get(CONF_DISCLAIMER_ACCEPTED):
                return await self.async_step_person()
            errors[CONF_DISCLAIMER_ACCEPTED] = "disclaimer_required"
        return self.async_show_form(
            step_id="user", data_schema=DISCLAIMER_SCHEMA, errors=errors
        )

    async def async_step_person(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the person's name and glucose sensor."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = str(user_input[CONF_NAME]).strip()
            if not name:
                errors[CONF_NAME] = "name_required"
            errors |= _validate_glucose_value(
                self.hass, CONF_GLUCOSE_ENTITY, user_input[CONF_GLUCOSE_ENTITY]
            )
            if not errors:
                self._name = name
                self._options = _clean_options(user_input)
                if _other_entries_monitoring(
                    self.hass, self._options[CONF_GLUCOSE_ENTITY], None
                ):
                    return await self.async_step_already_monitored()
                return await self.async_step_sources()
        return self.async_show_form(
            step_id="person",
            data_schema=self.add_suggested_values_to_schema(PERSON_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_already_monitored(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Tell the user that another entry already monitors the glucose sensor."""
        if user_input is not None:
            return await self.async_step_sources()
        entity_id = self._options[CONF_GLUCOSE_ENTITY]
        return self.async_show_form(
            step_id="already_monitored",
            data_schema=ALREADY_MONITORED_SCHEMA,
            description_placeholders=_already_monitored_placeholders(
                entity_id, _other_entries_monitoring(self.hass, entity_id, None)
            ),
        )

    async def async_step_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the optional sensors and the unit, if the sensors have none."""
        errors: dict[str, str] = {}
        if user_input is not None:
            options = {**self._options, **user_input}
            if not (errors := _validate_sources(self.hass, options)):
                return self.async_create_entry(
                    title=self._name,
                    data={CONF_NAME: self._name},
                    options=_clean_options(options),
                )
        suggestions = user_input or async_suggest_sources(
            self.hass, self._options[CONF_GLUCOSE_ENTITY]
        )
        return self.async_show_form(
            step_id="sources",
            data_schema=self.add_suggested_values_to_schema(
                SOURCES_SCHEMA, suggestions
            ),
            errors=errors,
            description_placeholders={"name": self._name},
        )


class OptionsFlowHandler(OptionsFlowWithReload):
    """Change the source entities of a monitored person."""

    def __init__(self) -> None:
        """Initialize the options flow."""
        self._options: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the source entities."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_glucose_value(
                self.hass, CONF_GLUCOSE_ENTITY, user_input[CONF_GLUCOSE_ENTITY]
            ) | _validate_sources(self.hass, user_input)
            if not errors:
                self._options = _clean_options(user_input)
                glucose_entity = self._options[CONF_GLUCOSE_ENTITY]
                # Only show the notice when the sensor changes, not on every save.
                if glucose_entity != self.config_entry.options.get(
                    CONF_GLUCOSE_ENTITY
                ) and _other_entries_monitoring(
                    self.hass, glucose_entity, self.config_entry.entry_id
                ):
                    return await self.async_step_already_monitored()
                return self._async_save()
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, user_input or self.config_entry.options
            ),
            errors=errors,
        )

    async def async_step_already_monitored(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Tell the user that another entry already monitors the glucose sensor."""
        if user_input is not None:
            return self._async_save()
        entity_id = self._options[CONF_GLUCOSE_ENTITY]
        return self.async_show_form(
            step_id="already_monitored",
            data_schema=ALREADY_MONITORED_SCHEMA,
            description_placeholders=_already_monitored_placeholders(
                entity_id,
                _other_entries_monitoring(
                    self.hass, entity_id, self.config_entry.entry_id
                ),
            ),
        )

    @callback
    def _async_save(self) -> ConfigFlowResult:
        """Keep options of other steps, replace the source entities."""
        other_options = {
            key: value
            for key, value in self.config_entry.options.items()
            if key not in OPTION_KEYS
        }
        return self.async_create_entry(data=other_options | self._options)
