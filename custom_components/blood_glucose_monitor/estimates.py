"""GMI and estimated HbA1c from the long-term statistics of the glucose sensor.

The recorder keeps hourly means of sensors with a state class (long-term
statistics) for good. The mean over the period (90 days by default) gives the
glucose management indicator and the estimated HbA1c (``report.py``). Below
70 % of the period with data there is no estimate; nothing is guessed. A
glucose sensor without long-term statistics gets a repair issue.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import Event, EventStateChangedData, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_PERIOD,
    CONF_PERIOD_ENTITY,
    DOMAIN,
    DURATION_UNITS,
)
from .glucose import parse_number
from .report import (
    EstimateStats,
    compute_estimate,
    estimated_a1c,
    gmi,
    to_mmol_mol,
)
from .source import MG_DL, sensor_unit, state_value, to_mg_dl

if TYPE_CHECKING:
    from .monitor import AlarmMonitor

_LOGGER = logging.getLogger(__name__)

# The recorder compiles the statistics of an hour shortly after it ends.
UPDATE_MINUTE = 15
UNIT_CLASS = "blood_glucose_concentration"
GMI = "gmi"
ESTIMATED_A1C = "estimated_a1c"
FORMULAS = {GMI: gmi, ESTIMATED_A1C: estimated_a1c}


def no_statistics_issue(entry_id: str) -> str:
    """Return the repair issue ID for a glucose sensor without statistics."""
    return f"no_statistics_{entry_id}"


class EstimateTracker:
    """Compute GMI and estimated HbA1c once per hour."""

    def __init__(self, monitor: AlarmMonitor, options: dict[str, Any]) -> None:
        """Initialize."""
        self.monitor = monitor
        self.hass = monitor.hass
        self.options = options
        self.stats: EstimateStats | None = None
        self.start: datetime | None = None
        self.end: datetime | None = None
        self.days: float | None = None
        self._issue = False

    @property
    def period(self) -> timedelta | None:
        """Return the period; an entity wins over the number of days."""
        if entity_id := self.options.get(CONF_PERIOD_ENTITY):
            # An entity without a unit counts in days; another unit only if
            # it is a known time unit.
            unit = sensor_unit(self.hass, entity_id)
            factor = DURATION_UNITS.get(unit) if unit else DURATION_UNITS["d"]
            value = parse_number(state_value(self.hass.states.get(entity_id)))
            if factor is None or value is None or value <= 0:
                return None
            return timedelta(minutes=value * factor)
        if (days := self.options.get(CONF_PERIOD)) is None or days <= 0:
            return None
        return timedelta(days=float(days))

    @callback
    def async_start(self) -> None:
        """Compute now, then every hour and when the period entity changes."""
        entry = self.monitor.entry
        entry.async_on_unload(
            async_track_time_change(
                self.hass, self._async_time, minute=UPDATE_MINUTE, second=0
            )
        )
        if entity_id := self.options.get(CONF_PERIOD_ENTITY):
            entry.async_on_unload(
                async_track_state_change_event(
                    self.hass, [entity_id], self._async_period_changed
                )
            )
        self._async_schedule()

    @callback
    def _async_time(self, now: datetime) -> None:
        self._async_schedule()

    @callback
    def _async_period_changed(self, event: Event[EventStateChangedData]) -> None:
        self._async_schedule()

    @callback
    def _async_schedule(self) -> None:
        self.monitor.entry.async_create_background_task(
            self.hass,
            self.async_update(),
            f"blood_glucose_monitor estimate {self.monitor.entry.title}",
        )

    async def async_update(self) -> None:
        """Read the hourly means of the period and update the estimates."""
        period = self.period
        end = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
        if period is None:
            self.stats = self.start = self.end = self.days = None
        else:
            start = end - period
            self.start, self.end = start, end
            self.days = round(period.total_seconds() / 86400, 2)
            self.stats = await self._async_stats(start, end, period)
        self.monitor.async_notify_listeners()

    async def _async_stats(
        self, start: datetime, end: datetime, period: timedelta
    ) -> EstimateStats | None:
        """Return the mean of the hourly means of the glucose sensor."""
        if "recorder" not in self.hass.config.components:
            _LOGGER.debug("No recorder, no estimates")
            return None
        # Imported here: the recorder is optional.
        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.statistics import (
            get_metadata,
            statistics_during_period,
        )

        glucose = self.monitor.source.entities.glucose
        recorder = get_instance(self.hass)
        metadata = await recorder.async_add_executor_job(
            lambda: get_metadata(self.hass, statistic_ids={glucose})
        )
        self._async_set_issue(glucose not in metadata)
        if glucose not in metadata:
            return None
        meta = metadata[glucose][1]
        # Glucose statistics are converted by the recorder; statistics without
        # a unit class are read in their own unit, else the unit set by hand.
        converted = meta.get("unit_class") == UNIT_CLASS
        unit = (
            MG_DL
            if converted
            else meta.get("unit_of_measurement") or self.monitor.source.entities.unit
        )
        rows = await recorder.async_add_executor_job(
            statistics_during_period,
            self.hass,
            start,
            end,
            {glucose},
            "hour",
            {UNIT_CLASS: MG_DL} if converted else None,
            {"mean"},
        )
        means = [to_mg_dl(row.get("mean"), unit) for row in rows.get(glucose, [])]
        return compute_estimate(means, round(period.total_seconds() / 3600))

    @callback
    def _async_set_issue(self, missing: bool) -> None:
        if missing == self._issue:
            return
        self._issue = missing
        issue_id = no_statistics_issue(self.monitor.entry.entry_id)
        if missing:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="no_statistics",
                translation_placeholders={
                    "name": self.monitor.entry.title,
                    "entity_id": self.monitor.source.entities.glucose,
                },
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    def value(self, kind: str) -> float | None:
        """Return GMI or estimated HbA1c in percent, None without enough data."""
        stats = self.stats
        if stats is None or not stats.sufficient:
            return None
        assert stats.mean is not None
        return round(FORMULAS[kind](stats.mean), 2)

    def attributes(self, kind: str) -> dict[str, Any]:
        """Return the IFCC value, the mean, the coverage and the period."""
        stats = self.stats
        value = self.value(kind)
        unit = self.monitor.unit
        mean = None if stats is None else stats.mean
        return {
            "mmol_mol": None if value is None else round(to_mmol_mol(value)),
            "glucose_mean": self.monitor.display(mean, unit),
            "unit": unit,
            "coverage": None if stats is None else round(stats.coverage, 1),
            "period_days": self.days,
            "start": None if self.start is None else self.start.isoformat(),
            "end": None if self.end is None else self.end.isoformat(),
        }
