"""Tests for the dependency-free glucose model."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.blood_glucose_monitor.glucose import (
    GlucoseReading,
    Trend,
    parse_number,
    parse_timestamp,
    parse_trend,
)

NOW = datetime(2026, 11, 7, 14, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("112", 112.0),
        (5.4, 5.4),
        ("-3.5", -3.5),
        (None, None),
        ("unknown", None),
        ("unavailable", None),
        ("nan", None),
        ("inf", None),
        (True, None),
        ([], None),
    ],
)
def test_parse_number(value: object, expected: float | None) -> None:
    """Numbers are parsed, everything else is rejected."""
    assert parse_number(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("steady", Trend.STEADY),
        ("falling_quickly", Trend.FALLING_QUICKLY),
        ("Flat", Trend.STEADY),
        ("DoubleDown", Trend.FALLING_QUICKLY),
        ("TripleUp", Trend.RISING_VERY_QUICKLY),
        ("FortyFiveDown", Trend.FALLING_SLIGHTLY),
        ("NOT COMPUTABLE", Trend.NOT_COMPUTABLE),
        ("RATE OUT OF RANGE", Trend.RATE_OUT_OF_RANGE),
        ("Rising quickly", Trend.RISING_QUICKLY),
        ("Stable", Trend.STEADY),
        ("Decreasing fast", Trend.FALLING_QUICKLY),
        ("decreasing-slowly", Trend.FALLING_SLIGHTLY),
        ("Increasing", Trend.RISING),
        ("↘", Trend.FALLING_SLIGHTLY),
        ("⇊", Trend.FALLING_QUICKLY),
        ("↓↓", Trend.FALLING_QUICKLY),
        ("⬆️", Trend.RISING),
        (" ➡ ", Trend.STEADY),
        ("?", None),
        ("NONE", None),
        ("sideways", None),
        ("3", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_trend(value: object, expected: Trend | None) -> None:
    """State keys, Nightscout directions, common words and arrows are understood."""
    assert parse_trend(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-11-07T14:00:00+00:00", datetime(2026, 11, 7, 14, tzinfo=UTC)),
        ("2026-11-07 15:00:00+01:00", datetime(2026, 11, 7, 14, tzinfo=UTC)),
        ("2026-11-07T14:00:00Z", datetime(2026, 11, 7, 14, tzinfo=UTC)),
        ("2026-11-07T14:00:00", datetime(2026, 11, 7, 14, tzinfo=UTC)),
        (datetime(2026, 11, 7, 14), datetime(2026, 11, 7, 14, tzinfo=UTC)),
        (1_794_060_000, datetime(2026, 11, 7, 14, tzinfo=UTC)),
        (1_794_060_000_000, datetime(2026, 11, 7, 14, tzinfo=UTC)),
        ("1794060000000", datetime(2026, 11, 7, 14, tzinfo=UTC)),
        ("not a date", None),
        (None, None),
        (True, None),
    ],
)
def test_parse_timestamp(value: object, expected: datetime | None) -> None:
    """Datetimes, ISO strings and epoch values are parsed as aware UTC times."""
    assert parse_timestamp(value) == expected


def test_reading_age_and_staleness() -> None:
    """Age and staleness are derived from the reading time."""
    reading = GlucoseReading(value=112, reading_time=NOW - timedelta(minutes=12))
    assert reading.age(NOW) == timedelta(minutes=12)
    assert not reading.is_stale(NOW, timedelta(minutes=15))
    assert reading.is_stale(NOW, timedelta(minutes=10))


def test_reading_without_value_or_time_is_stale() -> None:
    """A reading without value or without time counts as stale."""
    assert GlucoseReading(value=None, reading_time=NOW).is_stale(
        NOW, timedelta(minutes=15)
    )
    no_time = GlucoseReading(value=112)
    assert no_time.age(NOW) is None
    assert no_time.is_stale(NOW, timedelta(minutes=15))


def test_reading_from_the_future_has_zero_age() -> None:
    """Clock skew must not produce a negative age."""
    reading = GlucoseReading(value=112, reading_time=NOW + timedelta(minutes=1))
    assert reading.age(NOW) == timedelta(0)


def test_trend_arrow() -> None:
    """Every trend has an arrow."""
    assert GlucoseReading(value=1, trend=Trend.FALLING_QUICKLY).trend_arrow == "⇊"
    assert GlucoseReading(value=1).trend_arrow is None
    assert all(GlucoseReading(value=1, trend=trend).trend_arrow for trend in Trend)
