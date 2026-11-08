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
from homeassistant.const import STATE_OFF, STATE_ON, UnitOfBloodGlucoseConcentration
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    BooleanSelector,
    DurationSelector,
    DurationSelectorConfig,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TimeSelector,
)
from homeassistant.util.unit_conversion import BloodGlucoseConcentrationConverter
import probatio as vol

from .const import (
    ALARM_CANNULA_CHANGE,
    ALARM_CHARGING,
    ALARM_DATA_LOSS,
    ALARM_DEFAULTS,
    ALARM_HIGH,
    ALARM_LOW,
    ALARM_RAPID_FALL,
    ALARM_RAPID_RISE,
    ALARM_RESERVOIR_CHANGE,
    ALARM_SENSOR_CHANGE,
    ALARM_URGENT_HIGH,
    ALARM_URGENT_LOW,
    ALARMS,
    CHANGE_ALARMS,
    CONF_BATTERY_ENTITY,
    CONF_BATTERY_LIMIT,
    CONF_BATTERY_LIMIT_ENTITY,
    CONF_CHANGE_ENTITY,
    CONF_CHARGING_ENTITY,
    CONF_CLEAR_OFFSET,
    CONF_DELAY,
    CONF_DETECTION,
    CONF_DISCLAIMER_ACCEPTED,
    CONF_DUE_TIME,
    CONF_DURATION,
    CONF_GLUCOSE_ENTITY,
    CONF_GLUCOSE_UNIT,
    CONF_LAST_CHANGE_ENTITY,
    CONF_MAX_AGE,
    CONF_NAME,
    CONF_ONLY_WHEN_HOME,
    CONF_PAUSE,
    CONF_PERSON_ENTITY,
    CONF_RATE_ENTITY,
    CONF_RATE_LIMIT,
    CONF_READING_TIME_ENTITY,
    CONF_REMINDER_TIME,
    CONF_REPEAT,
    CONF_REPORT,
    CONF_REPORT_ENTITY,
    CONF_SNOOZE,
    CONF_THRESHOLD_ENTITY,
    CONF_TIME_ENTITY,
    CONF_TREND_ENTITY,
    CONF_TREND_LEVEL,
    CONF_WARNING,
    CONF_WEAR_DURATION,
    CONF_WEAR_DURATION_ENTITY,
    DEFAULT_CLEAR_OFFSET,
    DEFAULT_PAUSE_DURATION,
    DEFAULT_RATE_LIMIT,
    DETECTION_RATE,
    DETECTIONS,
    DOMAIN,
    DURATION_UNITS,
    RATE_ALARMS,
    RATE_UNITS,
    THRESHOLD_ALARMS,
    THRESHOLD_TRANSLATION_KEYS,
    TREND_LEVELS,
)
from .glucose import parse_number, parse_timestamp, parse_trend
from .monitor import AlarmMonitor, duration
from .source import (
    MG_DL,
    async_suggest_related,
    async_suggest_sources,
    sensor_unit,
    state_value,
)

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
# Menu steps have no fields.
MENU_SCHEMA = vol.Schema({})


def _minutes(minimum: int = 0) -> NumberSelector:
    """Return a selector for a duration in minutes."""
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum,
            max=1440,
            step=1,
            unit_of_measurement="min",
            mode=NumberSelectorMode.BOX,
        )
    )


THRESHOLD_SELECTOR = EntitySelector(
    EntitySelectorConfig(domain=["sensor", "number", "input_number"])
)
CLEAR_OFFSET_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=0, max=100, step="any", mode=NumberSelectorMode.BOX)
)
THRESHOLD_ALARM_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_THRESHOLD_ENTITY): THRESHOLD_SELECTOR,
        vol.Required(CONF_CLEAR_OFFSET): CLEAR_OFFSET_SELECTOR,
        vol.Required(CONF_DELAY): _minutes(),
        vol.Required(CONF_REPEAT): _minutes(),
        vol.Required(CONF_SNOOZE): _minutes(1),
        vol.Required(CONF_ONLY_WHEN_HOME, default=False): BooleanSelector(),
    }
)
DATA_LOSS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MAX_AGE): _minutes(1),
        vol.Required(CONF_REPEAT): _minutes(),
        vol.Required(CONF_SNOOZE): _minutes(1),
        vol.Required(CONF_ONLY_WHEN_HOME, default=False): BooleanSelector(),
    }
)
PAUSE_SCHEMA = vol.Schema({vol.Required(CONF_DURATION): _minutes(1)})
REPORT_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_REPORT_ENTITY): EntitySelector(
            EntitySelectorConfig(domain=["schedule", "input_boolean", "binary_sensor"])
        )
    }
)
TIME_ENTITY_SELECTOR = EntitySelector(
    EntitySelectorConfig(domain=["input_datetime", "time", "sensor"])
)
DURATION_SELECTOR = DurationSelector(DurationSelectorConfig(enable_day=True))
CHANGE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_WEAR_DURATION): DURATION_SELECTOR,
        vol.Optional(CONF_WEAR_DURATION_ENTITY): THRESHOLD_SELECTOR,
        vol.Optional(CONF_LAST_CHANGE_ENTITY): EntitySelector(
            EntitySelectorConfig(domain=["sensor", "input_datetime", "datetime"])
        ),
        vol.Optional(CONF_DUE_TIME): TimeSelector(),
        vol.Optional(CONF_TIME_ENTITY): TIME_ENTITY_SELECTOR,
        vol.Optional(CONF_WARNING): DURATION_SELECTOR,
        vol.Required(CONF_REPEAT): _minutes(),
        vol.Required(CONF_SNOOZE): _minutes(1),
        vol.Required(CONF_ONLY_WHEN_HOME, default=False): BooleanSelector(),
    }
)
CHARGING_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_BATTERY_ENTITY): SENSOR_SELECTOR,
        vol.Optional(CONF_CHARGING_ENTITY): EntitySelector(
            EntitySelectorConfig(domain=["binary_sensor", "sensor"])
        ),
        vol.Required(CONF_REMINDER_TIME): TimeSelector(),
        vol.Optional(CONF_TIME_ENTITY): TIME_ENTITY_SELECTOR,
        vol.Required(CONF_BATTERY_LIMIT): NumberSelector(
            NumberSelectorConfig(
                min=0,
                max=100,
                step=1,
                unit_of_measurement="%",
                mode=NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(CONF_BATTERY_LIMIT_ENTITY): THRESHOLD_SELECTOR,
        vol.Required(CONF_REPEAT): _minutes(),
        vol.Required(CONF_SNOOZE): _minutes(1),
        vol.Required(CONF_ONLY_WHEN_HOME, default=False): BooleanSelector(),
    }
)
RATE_ALARM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DETECTION): SelectSelector(
            SelectSelectorConfig(
                options=list(DETECTIONS),
                translation_key=CONF_DETECTION,
                mode=SelectSelectorMode.LIST,
            )
        ),
        vol.Required(CONF_TREND_LEVEL): SelectSelector(
            SelectSelectorConfig(
                options=list(TREND_LEVELS),
                translation_key=CONF_TREND_LEVEL,
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(CONF_RATE_LIMIT): CLEAR_OFFSET_SELECTOR,
        vol.Optional(CONF_RATE_ENTITY): THRESHOLD_SELECTOR,
        vol.Required(CONF_DELAY): _minutes(),
        vol.Required(CONF_REPEAT): _minutes(),
        vol.Required(CONF_SNOOZE): _minutes(1),
        vol.Required(CONF_ONLY_WHEN_HOME, default=False): BooleanSelector(),
    }
)
ALARM_SCHEMAS = {
    ALARM_URGENT_LOW: THRESHOLD_ALARM_SCHEMA,
    ALARM_LOW: THRESHOLD_ALARM_SCHEMA,
    ALARM_HIGH: THRESHOLD_ALARM_SCHEMA,
    ALARM_URGENT_HIGH: THRESHOLD_ALARM_SCHEMA,
    ALARM_RAPID_FALL: RATE_ALARM_SCHEMA,
    ALARM_RAPID_RISE: RATE_ALARM_SCHEMA,
    ALARM_DATA_LOSS: DATA_LOSS_SCHEMA,
    ALARM_CHARGING: CHARGING_SCHEMA,
    ALARM_CANNULA_CHANGE: CHANGE_SCHEMA,
    ALARM_SENSOR_CHANGE: CHANGE_SCHEMA,
    ALARM_RESERVOIR_CHANGE: CHANGE_SCHEMA,
}

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


def _validate_threshold(
    hass: HomeAssistant, entity_id: str, manual_unit: str | None
) -> dict[str, str]:
    """Return form errors for a threshold entity."""
    if errors := _validate_glucose_value(hass, CONF_THRESHOLD_ENTITY, entity_id):
        return errors
    if sensor_unit(hass, entity_id) is None and not manual_unit:
        return {CONF_THRESHOLD_ENTITY: "threshold_unit_required"}
    return {}


def _validate_charging(
    hass: HomeAssistant, values: Mapping[str, Any]
) -> dict[str, str]:
    """Return form errors of the charging reminder."""
    battery = values.get(CONF_BATTERY_ENTITY)
    charging = values.get(CONF_CHARGING_ENTITY)
    if not battery and not charging:
        return {}  # switched off
    errors: dict[str, str] = {}
    for key, entity_id in (
        (CONF_BATTERY_ENTITY, battery),
        (CONF_CHARGING_ENTITY, charging),
    ):
        if not entity_id:
            errors[key] = "charging_entities_required"
    if battery and _unparsable(hass, battery, parse_number):
        errors[CONF_BATTERY_ENTITY] = "not_numeric"
    if charging and _unparsable(hass, charging, AlarmMonitor.charging_from_state):
        errors[CONF_CHARGING_ENTITY] = "unknown_charging_state"
    if (time_entity := values.get(CONF_TIME_ENTITY)) and _unparsable(
        hass, time_entity, AlarmMonitor.time_from_state
    ):
        errors[CONF_TIME_ENTITY] = "invalid_time"
    if (limit_entity := values.get(CONF_BATTERY_LIMIT_ENTITY)) and _unparsable(
        hass, limit_entity, parse_number
    ):
        errors[CONF_BATTERY_LIMIT_ENTITY] = "not_numeric"
    return errors


def _validate_change(hass: HomeAssistant, values: Mapping[str, Any]) -> dict[str, str]:
    """Return form errors of a change reminder."""
    errors: dict[str, str] = {}
    wear_entity = values.get(CONF_WEAR_DURATION_ENTITY)
    if wear_entity:
        if _unparsable(hass, wear_entity, parse_number):
            errors[CONF_WEAR_DURATION_ENTITY] = "not_numeric"
        # Nothing is guessed: the entity has to report a time unit.
        elif sensor_unit(hass, wear_entity) not in DURATION_UNITS:
            errors[CONF_WEAR_DURATION_ENTITY] = "duration_unit_required"
    if (last_change := values.get(CONF_LAST_CHANGE_ENTITY)) and _unparsable(
        hass, last_change, AlarmMonitor.datetime_from_state
    ):
        errors[CONF_LAST_CHANGE_ENTITY] = "invalid_datetime"
    if last_change and not wear_entity and not duration(values.get(CONF_WEAR_DURATION)):
        errors[CONF_WEAR_DURATION] = "wear_duration_required"
    if (time_entity := values.get(CONF_TIME_ENTITY)) and _unparsable(
        hass, time_entity, AlarmMonitor.time_from_state
    ):
        errors[CONF_TIME_ENTITY] = "invalid_time"
    return errors


def _suggest_phone(hass: HomeAssistant, person: str | None) -> dict[str, str]:
    """Suggest battery and charging sensors of the person's phone.

    The phone is found via the device trackers of the person; the sensors
    are matched like the mobile app names them.
    """
    if not person or (state := hass.states.get(person)) is None:
        return {}
    registry = er.async_get(hass)
    suggestions: dict[str, str] = {}
    for tracker in state.attributes.get("device_trackers") or []:
        if (entry := registry.async_get(tracker)) is None or not entry.device_id:
            continue
        for entity in sorted(
            er.async_entries_for_device(registry, entry.device_id),
            key=lambda entity: entity.entity_id,
        ):
            if entity.disabled_by is not None:
                continue
            entity_id = entity.entity_id
            if entity.domain == "sensor" and (
                entity.original_device_class == "battery"
                or entity_id.endswith("_battery_level")
            ):
                suggestions.setdefault(CONF_BATTERY_ENTITY, entity_id)
            elif (
                entity.domain == "binary_sensor" and entity_id.endswith("_is_charging")
            ) or (entity.domain == "sensor" and entity_id.endswith("_battery_state")):
                suggestions.setdefault(CONF_CHARGING_ENTITY, entity_id)
    return suggestions


def _validate_rate(hass: HomeAssistant, values: Mapping[str, Any]) -> dict[str, str]:
    """Return form errors for the rate limit of a rapid change alarm."""
    if entity_id := values.get(CONF_RATE_ENTITY):
        if _unparsable(hass, entity_id, parse_number):
            return {CONF_RATE_ENTITY: "not_numeric"}
        # Nothing is guessed: the entity has to report a rate unit.
        if sensor_unit(hass, entity_id) not in RATE_UNITS:
            return {CONF_RATE_ENTITY: "rate_unit_required"}
        return {}
    if not values.get(CONF_RATE_LIMIT):
        return {CONF_RATE_LIMIT: "rate_limit_required"}
    return {}


class OptionsFlowHandler(OptionsFlowWithReload):
    """Change the glucose data, the alarms and the pause of a person."""

    def __init__(self) -> None:
        """Initialize the options flow."""
        self._options: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show what can be configured."""
        return self.async_show_menu(
            step_id="init", menu_options=["sources", *ALARMS, CONF_REPORT, CONF_PAUSE]
        )

    async def async_step_sources(
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
                return self._async_save_sources()
        return self.async_show_form(
            step_id="sources",
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
            return self._async_save_sources()
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

    async def async_step_urgent_low(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the urgent low alarm."""
        return await self._async_alarm_step(ALARM_URGENT_LOW, user_input)

    async def async_step_low(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the low alarm."""
        return await self._async_alarm_step(ALARM_LOW, user_input)

    async def async_step_high(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the high alarm."""
        return await self._async_alarm_step(ALARM_HIGH, user_input)

    async def async_step_urgent_high(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the urgent high alarm."""
        return await self._async_alarm_step(ALARM_URGENT_HIGH, user_input)

    async def async_step_rapid_fall(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the rapid fall alarm."""
        return await self._async_alarm_step(ALARM_RAPID_FALL, user_input)

    async def async_step_rapid_rise(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the rapid rise alarm."""
        return await self._async_alarm_step(ALARM_RAPID_RISE, user_input)

    async def async_step_data_loss(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the data loss alarm."""
        return await self._async_alarm_step(ALARM_DATA_LOSS, user_input)

    async def async_step_charging(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the charging reminder."""
        return await self._async_alarm_step(ALARM_CHARGING, user_input)

    async def async_step_cannula_change(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the cannula change reminder."""
        return await self._async_alarm_step(ALARM_CANNULA_CHANGE, user_input)

    async def async_step_sensor_change(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the sensor change reminder."""
        return await self._async_alarm_step(ALARM_SENSOR_CHANGE, user_input)

    async def async_step_reservoir_change(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the reservoir change reminder."""
        return await self._async_alarm_step(ALARM_RESERVOIR_CHANGE, user_input)

    async def async_step_report(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the reports."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if (entity_id := user_input.get(CONF_REPORT_ENTITY)) and state_value(
                self.hass.states.get(entity_id)
            ) not in (None, STATE_ON, STATE_OFF):
                errors[CONF_REPORT_ENTITY] = "not_on_off"
            if not errors:
                return self._async_save(CONF_REPORT, user_input)
        return self.async_show_form(
            step_id=CONF_REPORT,
            data_schema=self.add_suggested_values_to_schema(
                REPORT_SCHEMA,
                user_input or self.config_entry.options.get(CONF_REPORT, {}),
            ),
            errors=errors,
        )

    async def async_step_pause(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the pause (all alarms except urgent low)."""
        if user_input is not None:
            return self._async_save(CONF_PAUSE, user_input)
        current = {
            CONF_DURATION: DEFAULT_PAUSE_DURATION,
            **self.config_entry.options.get(CONF_PAUSE, {}),
        }
        return self.async_show_form(
            step_id=CONF_PAUSE,
            data_schema=self.add_suggested_values_to_schema(PAUSE_SCHEMA, current),
        )

    async def _async_alarm_step(
        self, alarm: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Show and save the form of one alarm."""
        options = self.config_entry.options
        unit = (
            sensor_unit(self.hass, options[CONF_GLUCOSE_ENTITY])
            or options.get(CONF_GLUCOSE_UNIT)
            or MG_DL
        )
        errors: dict[str, str] = {}
        if user_input is not None:
            values = dict(user_input)
            # Without threshold a threshold alarm is off.
            if entity_id := values.get(CONF_THRESHOLD_ENTITY):
                errors |= _validate_threshold(
                    self.hass, entity_id, options.get(CONF_GLUCOSE_UNIT)
                )
            if alarm == ALARM_CHARGING:
                errors |= _validate_charging(self.hass, values)
            if alarm in CHANGE_ALARMS:
                errors |= _validate_change(self.hass, values)
            if values.get(CONF_DETECTION) == DETECTION_RATE:
                errors |= _validate_rate(self.hass, values)
            if values[CONF_ONLY_WHEN_HOME] and not options.get(CONF_PERSON_ENTITY):
                errors[CONF_ONLY_WHEN_HOME] = "person_required"
            if not errors:
                return self._async_save(alarm, values)
            current = user_input
        else:
            current = {**ALARM_DEFAULTS[alarm], **options.get(alarm, {})}
            if alarm in THRESHOLD_ALARMS:
                current.setdefault(CONF_CLEAR_OFFSET, DEFAULT_CLEAR_OFFSET[unit])
            if alarm == ALARM_CHARGING and alarm not in options:
                current |= _suggest_phone(self.hass, options.get(CONF_PERSON_ENTITY))
            if alarm in RATE_ALARMS:
                current.setdefault(CONF_RATE_LIMIT, DEFAULT_RATE_LIMIT[unit])
            # Suggest a threshold only before the alarm was ever saved: an
            # empty threshold switches the alarm off.
            if alarm in THRESHOLD_ALARMS and alarm not in options:
                current.setdefault(
                    CONF_THRESHOLD_ENTITY,
                    async_suggest_related(
                        self.hass,
                        options[CONF_GLUCOSE_ENTITY],
                        {THRESHOLD_TRANSLATION_KEYS[alarm]: CONF_THRESHOLD_ENTITY},
                    ).get(CONF_THRESHOLD_ENTITY),
                )
        return self.async_show_form(
            step_id=alarm,
            data_schema=self.add_suggested_values_to_schema(
                ALARM_SCHEMAS[alarm],
                {key: value for key, value in current.items() if value is not None},
            ),
            errors=errors,
            description_placeholders={"unit": unit},
        )

    @callback
    def _async_save(self, key: str, values: dict[str, Any]) -> ConfigFlowResult:
        """Replace the options of one alarm or the pause."""
        return self.async_create_entry(data={**self.config_entry.options, key: values})

    @callback
    def _async_save_sources(self) -> ConfigFlowResult:
        """Keep the other options, replace the source entities."""
        other_options = {
            key: value
            for key, value in self.config_entry.options.items()
            if key not in OPTION_KEYS
        }
        return self.async_create_entry(data=other_options | self._options)
