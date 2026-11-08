"""Tests for the dependency-free report statistics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.blood_glucose_monitor.report import compute_stats

START = datetime(2026, 11, 7, 22, tzinfo=UTC)
END = START + timedelta(hours=1)


def at(minutes: float) -> datetime:
    """Return START plus minutes."""
    return START + timedelta(minutes=minutes)


def test_time_weighted() -> None:
    """Values count for as long as they were the latest value."""
    stats = compute_stats([(at(-10), 100), (at(30), 200)], START, END, low=70, high=180)
    assert stats is not None
    assert stats.minimum == 100
    assert stats.maximum == 200
    assert stats.mean == pytest.approx(150)
    assert stats.below == 0
    assert stats.in_range == 50
    assert stats.above == 50
    assert stats.coverage == 100


def test_unknown_values_are_left_out() -> None:
    """Unknown periods count neither for the values nor the shares."""
    stats = compute_stats(
        [(at(0), 60), (at(15), None), (at(45), 120)], START, END, low=70, high=180
    )
    assert stats is not None
    assert stats.mean == pytest.approx(90)
    assert stats.below == 50
    assert stats.in_range == 50
    assert stats.coverage == 50


def test_without_thresholds() -> None:
    """Without both thresholds there are no range shares."""
    stats = compute_stats([(at(0), 100)], START, END, low=70)
    assert stats is not None
    assert stats.below is None
    assert stats.in_range is None
    assert stats.above is None


@pytest.mark.parametrize(
    ("samples", "end"),
    [
        ([], END),
        ([(at(0), None)], END),
        ([(at(0), 100)], START),
        ([(at(70), 100)], END),
    ],
)
def test_no_stats(samples: list, end: datetime) -> None:
    """No known value in the period gives no statistics."""
    assert compute_stats(samples, START, end) is None
