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
