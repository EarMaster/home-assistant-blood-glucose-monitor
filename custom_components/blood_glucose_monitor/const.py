"""Constants for the Blood Glucose Monitor integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "blood_glucose_monitor"

# Documentation site with the automation builder.
DOCS_URL: Final = "https://earmaster.github.io/home-assistant-blood-glucose-monitor/"
BUILDER_URL: Final = f"{DOCS_URL}builder.html"
# Languages of the documentation site besides English (under /<language>/).
DOCS_LANGUAGES: Final = ("de", "es", "fr", "nl")

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
ALARM_HIGH: Final = "high"
ALARM_URGENT_HIGH: Final = "urgent_high"
ALARM_RAPID_FALL: Final = "rapid_fall"
ALARM_RAPID_RISE: Final = "rapid_rise"
ALARM_DATA_LOSS: Final = "data_loss"
# Reminder to charge the phone, built on the alarm engine.
ALARM_CHARGING: Final = "charging"
# Reminders to change the cannula, the CGM sensor and the insulin reservoir.
ALARM_CANNULA_CHANGE: Final = "cannula_change"
ALARM_SENSOR_CHANGE: Final = "sensor_change"
ALARM_RESERVOIR_CHANGE: Final = "reservoir_change"
CHANGE_ALARMS: Final = (
    ALARM_CANNULA_CHANGE,
    ALARM_SENSOR_CHANGE,
    ALARM_RESERVOIR_CHANGE,
)
ALARMS: Final = (
    ALARM_URGENT_LOW,
    ALARM_LOW,
    ALARM_HIGH,
    ALARM_URGENT_HIGH,
    ALARM_RAPID_FALL,
    ALARM_RAPID_RISE,
    ALARM_DATA_LOSS,
    ALARM_CHARGING,
    *CHANGE_ALARMS,
)
# Alarms that do not depend on the glucose data (and its reading time).
ALARMS_WITHOUT_GLUCOSE: Final = (ALARM_CHARGING, *CHANGE_ALARMS)
# Alarm below / above a threshold entity.
LOW_ALARMS: Final = (ALARM_URGENT_LOW, ALARM_LOW)
HIGH_ALARMS: Final = (ALARM_HIGH, ALARM_URGENT_HIGH)
THRESHOLD_ALARMS: Final = (*LOW_ALARMS, *HIGH_ALARMS)
# Alarm on a fast change, from the trend of the source or an own rate.
RATE_ALARMS: Final = (ALARM_RAPID_FALL, ALARM_RAPID_RISE)
# Urgent low is never paused.
PAUSABLE_ALARMS: Final = tuple(alarm for alarm in ALARMS if alarm != ALARM_URGENT_LOW)

CONF_THRESHOLD_ENTITY: Final = "threshold_entity"
CONF_CLEAR_OFFSET: Final = "clear_offset"
CONF_DELAY: Final = "delay"
CONF_REPEAT: Final = "repeat"
CONF_SNOOZE: Final = "snooze"
CONF_MAX_AGE: Final = "max_age"
CONF_ONLY_WHEN_HOME: Final = "only_when_home"

# Rapid change alarms: how a fast change is detected.
CONF_DETECTION: Final = "detection"
DETECTION_OFF: Final = "off"
DETECTION_TREND: Final = "trend"
DETECTION_RATE: Final = "rate"
DETECTIONS: Final = (DETECTION_OFF, DETECTION_TREND, DETECTION_RATE)
CONF_TREND_LEVEL: Final = "trend_level"
TREND_LEVEL_QUICKLY: Final = "quickly"
TREND_LEVEL_VERY_QUICKLY: Final = "very_quickly"
TREND_LEVELS: Final = (TREND_LEVEL_QUICKLY, TREND_LEVEL_VERY_QUICKLY)
# Rate limit per minute, as number (unit of the glucose data) or entity.
CONF_RATE_LIMIT: Final = "rate_limit"
CONF_RATE_ENTITY: Final = "rate_entity"
# Units of a rate limit entity and the glucose unit they stand for.
RATE_UNITS: Final = {"mg/dL/min": "mg/dL", "mmol/L/min": "mmol/L"}
# A rate needs two readings at most this many minutes apart.
MAX_RATE_GAP_MINUTES: Final = 15

# Charging reminder: alarm from the reminder time until midnight while the
# phone is not charging and the battery is at or below the limit.
CONF_BATTERY_ENTITY: Final = "battery_entity"
CONF_CHARGING_ENTITY: Final = "charging_entity"
CONF_REMINDER_TIME: Final = "reminder_time"
CONF_TIME_ENTITY: Final = "time_entity"
CONF_BATTERY_LIMIT: Final = "battery_limit"
CONF_BATTERY_LIMIT_ENTITY: Final = "battery_limit_entity"
# States of a charging sensor (mobile app battery state), lower case.
CHARGING_STATES: Final = ("charging", "full")
NOT_CHARGING_STATES: Final = (
    "discharging",
    "not_charging",
    "not charging",
    "unplugged",
)

# Change reminders: due at the last change plus the wear duration, or at a
# fixed time on that day. The last change comes from an entity or is
# recorded by the integration (button, action).
CONF_WEAR_DURATION: Final = "wear_duration"
CONF_WEAR_DURATION_ENTITY: Final = "wear_duration_entity"
CONF_LAST_CHANGE_ENTITY: Final = "last_change_entity"
CONF_DUE_TIME: Final = "due_time"
CONF_WARNING: Final = "warning"
# Units of a wear duration entity in minutes.
DURATION_UNITS: Final = {"d": 1440, "h": 60, "min": 1}
TRIGGER_SOON: Final = "soon"
"""Change due soon (warning before the reminder)."""
SERVICE_RECORD_CHANGE: Final = "record_change"
ATTR_CHANGE: Final = "change"
ATTR_TIME: Final = "time"

# Reports: one report per period in which the report entity (e.g. a schedule)
# is on. Options dict under this key.
CONF_REPORT: Final = "report"
CONF_REPORT_ENTITY: Final = "report_entity"
TRIGGER_REPORT: Final = "report"

# Pause of the pausable alarms, options dict under this key.
CONF_PAUSE: Final = "pause"
CONF_DURATION: Final = "duration"

# Defaults in minutes. Only suggestions, every value can be changed.
ALARM_DEFAULTS: Final[dict[str, dict[str, int | str]]] = {
    ALARM_URGENT_LOW: {CONF_DELAY: 0, CONF_REPEAT: 5, CONF_SNOOZE: 10},
    ALARM_LOW: {CONF_DELAY: 5, CONF_REPEAT: 5, CONF_SNOOZE: 15},
    ALARM_HIGH: {CONF_DELAY: 30, CONF_REPEAT: 30, CONF_SNOOZE: 120},
    ALARM_URGENT_HIGH: {CONF_DELAY: 15, CONF_REPEAT: 15, CONF_SNOOZE: 60},
    ALARM_RAPID_FALL: {
        CONF_DETECTION: DETECTION_OFF,
        CONF_TREND_LEVEL: TREND_LEVEL_QUICKLY,
        CONF_DELAY: 0,
        CONF_REPEAT: 0,
        CONF_SNOOZE: 30,
    },
    ALARM_RAPID_RISE: {
        CONF_DETECTION: DETECTION_OFF,
        CONF_TREND_LEVEL: TREND_LEVEL_QUICKLY,
        CONF_DELAY: 0,
        CONF_REPEAT: 0,
        CONF_SNOOZE: 30,
    },
    ALARM_DATA_LOSS: {CONF_MAX_AGE: 20, CONF_REPEAT: 15, CONF_SNOOZE: 30},
    ALARM_CHARGING: {
        CONF_REMINDER_TIME: "20:00:00",
        CONF_BATTERY_LIMIT: 75,
        CONF_REPEAT: 0,
        CONF_SNOOZE: 30,
    },
    **{alarm: {CONF_REPEAT: 0, CONF_SNOOZE: 60} for alarm in CHANGE_ALARMS},
}
DEFAULT_PAUSE_DURATION: Final = 60
# Clear offset suggested per glucose unit.
DEFAULT_CLEAR_OFFSET: Final = {"mg/dL": 10, "mmol/L": 0.5}
# Rate limit suggested per glucose unit (per minute).
DEFAULT_RATE_LIMIT: Final = {"mg/dL": 3, "mmol/L": 0.17}

# Translation keys of threshold sensors (Nightscout) suggested per alarm.
THRESHOLD_TRANSLATION_KEYS: Final = {
    ALARM_URGENT_LOW: "urgent_low_threshold",
    ALARM_LOW: "target_range_bottom",
    ALARM_HIGH: "target_range_top",
    ALARM_URGENT_HIGH: "urgent_high_threshold",
}

EVENT_MOBILE_APP_NOTIFICATION_ACTION: Final = "mobile_app_notification_action"
# Event types of the event entities: f"{alarm}_{TRIGGER_ALERT|TRIGGER_ENDED}".
TRIGGER_ALERT: Final = "alert"
"""Alarm started or repeated."""
TRIGGER_ENDED: Final = "ended"
"""Alarm acknowledged or over."""
SERVICE_ACKNOWLEDGE: Final = "acknowledge"
ATTR_ALARM: Final = "alarm"
ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
