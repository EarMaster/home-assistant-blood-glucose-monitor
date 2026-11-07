"""Constants for the Blood Glucose Monitor integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "blood_glucose_monitor"

# Config entry data
CONF_NAME: Final = "name"

# Config entry options: source entities
CONF_GLUCOSE_ENTITY: Final = "glucose_entity"
CONF_PERSON_ENTITY: Final = "person_entity"
CONF_TREND_ENTITY: Final = "trend_entity"
CONF_CHANGE_ENTITY: Final = "change_entity"
CONF_READING_TIME_ENTITY: Final = "reading_time_entity"
# Unit of source sensors that do not report one. Never guessed.
CONF_GLUCOSE_UNIT: Final = "glucose_unit"

SOURCE_ENTITY_KEYS: Final = (
    CONF_GLUCOSE_ENTITY,
    CONF_TREND_ENTITY,
    CONF_CHANGE_ENTITY,
    CONF_READING_TIME_ENTITY,
)

# Config flow only
CONF_DISCLAIMER_ACCEPTED: Final = "disclaimer_accepted"

# State attributes some glucose integrations (e.g. Nightscout) expose on the
# glucose sensor itself. Used as fallback when no dedicated entity is selected.
ATTR_SOURCE_DATE: Final = "date"
ATTR_SOURCE_DELTA: Final = "delta"
ATTR_SOURCE_DIRECTION: Final = "direction"

# Translation keys of dedicated source sensors (Dexcom, Nightscout) used to
# suggest the matching entities during setup.
SOURCE_TRANSLATION_KEY_TREND: Final = "glucose_trend"
SOURCE_TRANSLATION_KEY_CHANGE: Final = "glucose_change"
SOURCE_TRANSLATION_KEY_READING_TIME: Final = "glucose_reading_time"

# Alarms. Each alarm has its own options dict under its name in the entry
# options, and its own acknowledge/snooze state.
ALARM_URGENT_LOW: Final = "urgent_low"
ALARM_LOW: Final = "low"
ALARM_DATA_LOSS: Final = "data_loss"
ALARMS: Final = (ALARM_URGENT_LOW, ALARM_LOW, ALARM_DATA_LOSS)
THRESHOLD_ALARMS: Final = (ALARM_URGENT_LOW, ALARM_LOW)
# Urgent low is never paused.
PAUSABLE_ALARMS: Final = (ALARM_LOW, ALARM_DATA_LOSS)

CONF_THRESHOLD_ENTITY: Final = "threshold_entity"
CONF_CLEAR_OFFSET: Final = "clear_offset"
CONF_DELAY: Final = "delay"
CONF_REPEAT: Final = "repeat"
CONF_SNOOZE: Final = "snooze"
CONF_MAX_AGE: Final = "max_age"
CONF_ONLY_WHEN_HOME: Final = "only_when_home"

# Pause of the pausable alarms, options dict under this key.
CONF_PAUSE: Final = "pause"
CONF_DURATION: Final = "duration"

# Defaults in minutes. Only suggestions, every value can be changed.
ALARM_DEFAULTS: Final[dict[str, dict[str, int]]] = {
    ALARM_URGENT_LOW: {CONF_DELAY: 0, CONF_REPEAT: 5, CONF_SNOOZE: 10},
    ALARM_LOW: {CONF_DELAY: 5, CONF_REPEAT: 5, CONF_SNOOZE: 15},
    ALARM_DATA_LOSS: {CONF_MAX_AGE: 20, CONF_REPEAT: 15, CONF_SNOOZE: 30},
}
DEFAULT_PAUSE_DURATION: Final = 60
# Clear offset suggested per glucose unit.
DEFAULT_CLEAR_OFFSET: Final = {"mg/dL": 10, "mmol/L": 0.5}

# Translation keys of threshold sensors (Nightscout) suggested per alarm.
THRESHOLD_TRANSLATION_KEYS: Final = {
    ALARM_URGENT_LOW: "urgent_low_threshold",
    ALARM_LOW: "target_range_bottom",
}

EVENT_MOBILE_APP_NOTIFICATION_ACTION: Final = "mobile_app_notification_action"
# Fired for every alarm event; the device triggers listen to it. The data
# contains "type" (f"{alarm}_{TRIGGER_ALERT|TRIGGER_ENDED}") and "device_id".
EVENT_ALARM: Final = f"{DOMAIN}_alarm"
TRIGGER_ALERT: Final = "alert"
"""Alarm started or repeated."""
TRIGGER_ENDED: Final = "ended"
"""Alarm acknowledged or over."""
SERVICE_ACKNOWLEDGE: Final = "acknowledge"
ATTR_ALARM: Final = "alarm"
ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
