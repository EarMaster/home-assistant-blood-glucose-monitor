"""Config flow for the Blood Glucose Monitor integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    TextSelector,
)
from homeassistant.util.unit_conversion import BloodGlucoseConcentrationConverter
import probatio as vol

from .const import (
    CONF_CHANGE_ENTITY,
    CONF_DISCLAIMER_ACCEPTED,
    CONF_GLUCOSE_ENTITY,
    CONF_NAME,
    CONF_PERSON_ENTITY,
    CONF_READING_TIME_ENTITY,
    CONF_TREND_ENTITY,
    DOMAIN,
)
from .source import async_suggest_sources

GLUCOSE_SELECTOR = EntitySelector(
    EntitySelectorConfig(
        domain="sensor", device_class=SensorDeviceClass.BLOOD_GLUCOSE_CONCENTRATION
    )
)
PERSON_SELECTOR = EntitySelector(EntitySelectorConfig(domain="person"))
TREND_SELECTOR = EntitySelector(
    EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.ENUM)
)
CHANGE_SELECTOR = EntitySelector(
    EntitySelectorConfig(
        domain="sensor", device_class=SensorDeviceClass.BLOOD_GLUCOSE_CONCENTRATION
    )
)
READING_TIME_SELECTOR = EntitySelector(
    EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.TIMESTAMP)
)

DISCLAIMER_SCHEMA = vol.Schema(
    {vol.Required(CONF_DISCLAIMER_ACCEPTED, default=False): BooleanSelector()}
)
PERSON_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): TextSelector(),
        vol.Required(CONF_GLUCOSE_ENTITY): GLUCOSE_SELECTOR,
        vol.Optional(CONF_PERSON_ENTITY): PERSON_SELECTOR,
    }
)
SOURCES_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_TREND_ENTITY): TREND_SELECTOR,
        vol.Optional(CONF_CHANGE_ENTITY): CHANGE_SELECTOR,
        vol.Optional(CONF_READING_TIME_ENTITY): READING_TIME_SELECTOR,
    }
)
OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_GLUCOSE_ENTITY): GLUCOSE_SELECTOR,
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
)


def _clean_options(values: Mapping[str, Any]) -> dict[str, Any]:
    """Keep known option keys, drop empty values."""
    return {key: values[key] for key in OPTION_KEYS if values.get(key)}


def _validate_glucose_entity(hass: HomeAssistant, entity_id: str) -> dict[str, str]:
    """Return form errors for the selected glucose sensor."""
    if (state := hass.states.get(entity_id)) is not None and state.attributes.get(
        ATTR_UNIT_OF_MEASUREMENT
    ) not in (None, *BloodGlucoseConcentrationConverter.VALID_UNITS):
        return {CONF_GLUCOSE_ENTITY: "unsupported_unit"}
    return {}


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
            errors |= _validate_glucose_entity(
                self.hass, user_input[CONF_GLUCOSE_ENTITY]
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
        """Ask for the optional trend, change and reading time sensors."""
        if user_input is not None:
            options = _clean_options({**self._options, **user_input})
            return self.async_create_entry(
                title=self._name, data={CONF_NAME: self._name}, options=options
            )
        suggestions = async_suggest_sources(
            self.hass, self._options[CONF_GLUCOSE_ENTITY]
        )
        return self.async_show_form(
            step_id="sources",
            data_schema=self.add_suggested_values_to_schema(
                SOURCES_SCHEMA, suggestions
            ),
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
            errors = _validate_glucose_entity(
                self.hass, user_input[CONF_GLUCOSE_ENTITY]
            )
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
