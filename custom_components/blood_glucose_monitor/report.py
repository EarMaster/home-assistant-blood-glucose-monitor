"""Statistics of a report period.

This module has no Home Assistant dependencies. All glucose values are in
mg/dL. The statistics are weighted by time: a value counts for as long as it
was the latest value, so repeated equal readings (which the recorder does not
store as changes) do not distort the result.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ReportStats:
    """Glucose statistics of one period."""

    minimum: float
    maximum: float
    mean: float
    """Time weighted mean."""

    below: float | None
    """Share of the time below the low threshold in percent."""

    in_range: float | None
    """Share of the time within the thresholds in percent."""

    above: float | None
    """Share of the time above the high threshold in percent."""

    coverage: float
    """Share of the period with a known value in percent."""


def compute_stats(
    samples: Sequence[tuple[datetime, float | None]],
    start: datetime,
    end: datetime,
    low: float | None = None,
    high: float | None = None,
) -> ReportStats | None:
    """Return the statistics of ``samples`` between ``start`` and ``end``.

    ``samples`` are (time, value) pairs sorted by time; ``None`` stands for an
    unknown value (e.g. unavailable). A sample before ``start`` gives the value
    at the start. The range shares need both thresholds. Returns ``None``
    without any known value in the period.
    """
    total = (end - start).total_seconds()
    if total <= 0:
        return None
    weights: list[tuple[float, float]] = []
    for index, (time, value) in enumerate(samples):
        begin = max(time, start)
        until = samples[index + 1][0] if index + 1 < len(samples) else end
        until = min(until, end)
        seconds = (until - begin).total_seconds()
        if value is None or seconds <= 0:
            continue
        weights.append((value, seconds))
    if not weights:
        return None

    known = sum(seconds for _, seconds in weights)
    mean = sum(value * seconds for value, seconds in weights) / known
    below = in_range = above = None
    if low is not None and high is not None:
        below = _share(weights, known, lambda value: value < low)
        above = _share(weights, known, lambda value: value > high)
        in_range = round(100 - below - above, 1)
    return ReportStats(
        minimum=min(value for value, _ in weights),
        maximum=max(value for value, _ in weights),
        mean=mean,
        below=below,
        in_range=in_range,
        above=above,
        coverage=round(100 * known / total, 1),
    )


def _share(weights: list[tuple[float, float]], known: float, test: object) -> float:
    """Return the share of the known time where ``test(value)`` is true."""
    assert callable(test)
    seconds = sum(seconds for value, seconds in weights if test(value))
    return round(100 * seconds / known, 1)


# Estimates of the HbA1c from the mean glucose over a long period. Below this
# share of the period with data no estimate is given (usual CGM rule).
MIN_ESTIMATE_COVERAGE = 70.0


def gmi(mean: float) -> float:
    """Return the glucose management indicator in percent (Bergenstal 2018)."""
    return 3.31 + 0.02392 * mean


def estimated_a1c(mean: float) -> float:
    """Return the estimated HbA1c in percent (ADAG, Nathan 2008)."""
    return (mean + 46.7) / 28.7


def to_mmol_mol(percent: float) -> float:
    """Convert an HbA1c in percent (NGSP) to mmol/mol (IFCC)."""
    return (percent - 2.15) * 10.929


@dataclass(frozen=True, slots=True)
class EstimateStats:
    """Mean glucose of a long period from hourly means."""

    mean: float | None
    """Mean in mg/dL, None without any data."""

    coverage: float
    """Share of the hours of the period with data in percent."""

    @property
    def sufficient(self) -> bool:
        """Return True if the period has enough data for an estimate."""
        return self.mean is not None and self.coverage >= MIN_ESTIMATE_COVERAGE


def compute_estimate(hourly_means: Sequence[float | None], hours: int) -> EstimateStats:
    """Return the mean of the hourly means and the share of hours with data."""
    values = [value for value in hourly_means if value is not None]
    if not values or hours <= 0:
        return EstimateStats(mean=None, coverage=0.0)
    return EstimateStats(
        mean=sum(values) / len(values),
        coverage=min(100.0, 100 * len(values) / hours),
    )
