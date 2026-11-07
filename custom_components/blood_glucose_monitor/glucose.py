"""Glucose reading model and parsers.

This module has no Home Assistant dependencies so the core logic can be unit
tested in isolation. All glucose values in this module are in mg/dL; unit
conversion happens where Home Assistant states are read (see ``source.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import math


class Trend(StrEnum):
    """Glucose trend.

    The values match the state keys of the ``glucose_trend`` sensors of the
    Dexcom and Nightscout integrations.
    """

    RISING_VERY_QUICKLY = "rising_very_quickly"
    RISING_QUICKLY = "rising_quickly"
    RISING = "rising"
    RISING_SLIGHTLY = "rising_slightly"
    STEADY = "steady"
    FALLING_SLIGHTLY = "falling_slightly"
    FALLING = "falling"
    FALLING_QUICKLY = "falling_quickly"
    FALLING_VERY_QUICKLY = "falling_very_quickly"
    NOT_COMPUTABLE = "not_computable"
    RATE_OUT_OF_RANGE = "rate_out_of_range"


TREND_ARROWS: dict[Trend, str] = {
    Trend.RISING_VERY_QUICKLY: "⤊",
    Trend.RISING_QUICKLY: "⇈",
    Trend.RISING: "↑",
    Trend.RISING_SLIGHTLY: "↗",
    Trend.STEADY: "→",
    Trend.FALLING_SLIGHTLY: "↘",
    Trend.FALLING: "↓",
    Trend.FALLING_QUICKLY: "⇊",
    Trend.FALLING_VERY_QUICKLY: "⤋",
    Trend.NOT_COMPUTABLE: "?",
    Trend.RATE_OUT_OF_RANGE: "⇕",
}

# Raw Nightscout directions (``direction`` attribute of the Nightscout glucose
# sensor), see Nightscout lib/plugins/direction.js. Keys are casefolded.
_NIGHTSCOUT_DIRECTIONS: dict[str, Trend] = {
    "tripleup": Trend.RISING_VERY_QUICKLY,
    "doubleup": Trend.RISING_QUICKLY,
    "singleup": Trend.RISING,
    "fortyfiveup": Trend.RISING_SLIGHTLY,
    "flat": Trend.STEADY,
    "fortyfivedown": Trend.FALLING_SLIGHTLY,
    "singledown": Trend.FALLING,
    "doubledown": Trend.FALLING_QUICKLY,
    "tripledown": Trend.FALLING_VERY_QUICKLY,
    "not computable": Trend.NOT_COMPUTABLE,
    "rate out of range": Trend.RATE_OUT_OF_RANGE,
}

# Epoch values above this are treated as milliseconds (Nightscout uses ms).
_EPOCH_MS_THRESHOLD = 100_000_000_000


class ReadingTimeSource(StrEnum):
    """Where the time of the reading came from."""

    ENTITY = "entity"
    ATTRIBUTE = "attribute"
    LAST_CHANGED = "last_changed"


@dataclass(frozen=True, slots=True)
class GlucoseReading:
    """Snapshot of the latest glucose reading of one person."""

    value: float | None
    """Glucose value in mg/dL, ``None`` if unknown or unavailable."""

    trend: Trend | None = None
    change: float | None = None
    """Change to the previous reading in mg/dL."""

    reading_time: datetime | None = None
    reading_time_source: ReadingTimeSource | None = None

    @property
    def trend_arrow(self) -> str | None:
        """Return an arrow symbol for the trend."""
        return None if self.trend is None else TREND_ARROWS[self.trend]

    def age(self, now: datetime) -> timedelta | None:
        """Return how old the reading is, ``None`` if the time is unknown."""
        if self.reading_time is None:
            return None
        return max(now - self.reading_time, timedelta(0))

    def is_stale(self, now: datetime, max_age: timedelta) -> bool:
        """Return True if no valid reading newer than ``max_age`` exists."""
        if self.value is None:
            return True
        age = self.age(now)
        return age is None or age > max_age


def parse_number(value: object) -> float | None:
    """Return ``value`` as finite float, ``None`` if it is not a number."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return None
    return number if math.isfinite(number) else None


def parse_trend(value: object) -> Trend | None:
    """Parse a trend from an enum state key or a raw Nightscout direction."""
    if value is None:
        return None
    text = str(value).strip()
    try:
        return Trend(text.lower())
    except ValueError:
        return _NIGHTSCOUT_DIRECTIONS.get(text.casefold())


def parse_timestamp(value: object) -> datetime | None:
    """Parse a reading time.

    Accepts aware or naive datetimes (naive is treated as UTC), ISO 8601
    strings and epoch values in seconds or milliseconds.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, int | float):
        if not math.isfinite(value):
            return None
        seconds = value / 1000 if abs(value) > _EPOCH_MS_THRESHOLD else value
        try:
            result = datetime.fromtimestamp(seconds, UTC)
        except OverflowError, OSError, ValueError:
            return None
    elif isinstance(value, str):
        text = value.strip()
        if (number := parse_number(text)) is not None:
            return parse_timestamp(number)
        try:
            result = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result
