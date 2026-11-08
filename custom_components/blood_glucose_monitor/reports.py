"""Reports: one report per period in which the report entity is on.

The report entity is typically a schedule helper with several blocks (e.g.
night and school). When a block ends, the glucose history of the block is
summarized (``report.py``) and the "report" device trigger fires with the
statistics, the start and the end of the block.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, STATE_OFF, STATE_ON
from homeassistant.core import Event, EventStateChangedData, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import ALARM_LOW, ALARM_URGENT_LOW, TRIGGER_REPORT
from .glucose import parse_number
from .report import ReportStats, compute_stats
from .source import state_value, to_mg_dl

if TYPE_CHECKING:
    from .monitor import AlarmMonitor

_LOGGER = logging.getLogger(__name__)


class ReportTracker:
    """Track the periods of the report entity and report each period."""

    def __init__(
        self, monitor: AlarmMonitor, entity_id: str, *, only_when_home: bool = False
    ) -> None:
        """Initialize."""
        self.monitor = monitor
        self.hass = monitor.hass
        self.entity_id = entity_id
        # The report is always made; only the trigger depends on presence.
        self.only_when_home = only_when_home
        self.start: datetime | None = None
        self.counts: dict[str, int] = {}
        self.last: dict[str, Any] | None = None

    def restore(self, data: dict[str, Any]) -> None:
        """Restore a running period and the last report."""
        self.start = _parse(data.get("start"))
        self.counts = dict(data.get("counts") or {})
        self.last = data.get("last")

    def as_dict(self) -> dict[str, Any]:
        """Return the data to store."""
        return {
            "start": None if self.start is None else self.start.isoformat(),
            "counts": self.counts,
            "last": self.last,
        }

    @callback
    def async_start(self) -> None:
        """Follow the report entity; catch up on changes during a restart."""
        self.monitor.entry.async_on_unload(
            async_track_state_change_event(
                self.hass, [self.entity_id], self._async_state_changed
            )
        )
        state = self.hass.states.get(self.entity_id)
        if state is None:
            return
        if state.state == STATE_ON and self.start is None:
            self._begin(state.last_changed)
        elif state.state == STATE_OFF and self.start is not None:
            self._end(max(state.last_changed, self.start))

    @callback
    def count(self, alarm: str) -> None:
        """Count an alarm that started during a period."""
        if self.start is not None:
            self.counts[alarm] = self.counts.get(alarm, 0) + 1

    @callback
    def _async_state_changed(self, event: Event[EventStateChangedData]) -> None:
        new = event.data["new_state"]
        if new is None:
            return
        if new.state == STATE_ON and self.start is None:
            self._begin(new.last_changed)
        elif new.state == STATE_OFF and self.start is not None:
            self._end(new.last_changed)

    def _begin(self, start: datetime) -> None:
        self.start = start
        self.counts = {}
        self.monitor.async_save()

    def _end(self, end: datetime) -> None:
        start, counts = self.start, self.counts
        assert start is not None
        self.start = None
        self.counts = {}
        self.monitor.async_save()
        self.monitor.entry.async_create_background_task(
            self.hass,
            self._async_report(start, end, counts),
            f"blood_glucose_monitor report {self.monitor.entry.title}",
        )

    async def _async_report(
        self, start: datetime, end: datetime, counts: dict[str, int]
    ) -> None:
        """Summarize a period and fire the report trigger."""
        stats = await self._async_stats(start, end)
        monitor = self.monitor
        unit = monitor.unit
        display = monitor.display
        low_alarms = counts.get(ALARM_LOW, 0) + counts.get(ALARM_URGENT_LOW, 0)
        data: dict[str, Any] = {
            "entry_id": monitor.entry.entry_id,
            "person_name": monitor.entry.title,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "duration_min": int((end - start).total_seconds() // 60),
            "unit": unit,
            "glucose_min": None if stats is None else display(stats.minimum, unit),
            "glucose_max": None if stats is None else display(stats.maximum, unit),
            "glucose_mean": None if stats is None else display(stats.mean, unit),
            "below": None if stats is None else stats.below,
            "in_range": None if stats is None else stats.in_range,
            "above": None if stats is None else stats.above,
            "coverage": None if stats is None else stats.coverage,
            "alarms": dict(counts),
            "low_alarms": low_alarms,
        }
        data["title"] = monitor.text("report", name=monitor.entry.title)
        data["message"] = self._message(stats, data, start, end)
        self.last = data
        monitor.async_save()
        if not self.only_when_home or monitor.at_home:
            monitor.async_fire(TRIGGER_REPORT, data)
        monitor.async_notify_listeners()

    def _message(
        self,
        stats: ReportStats | None,
        data: dict[str, Any],
        start: datetime,
        end: datetime,
    ) -> str:
        period = f"{dt_util.as_local(start):%H:%M}–{dt_util.as_local(end):%H:%M}"
        if stats is None:
            return self.monitor.text("report_no_data", period=period)
        key = (
            "report_message"
            if stats.in_range is not None
            else "report_message_no_range"
        )
        return self.monitor.text(
            key,
            period=period,
            in_range=_number(data["in_range"]),
            below=_number(data["below"]),
            above=_number(data["above"]),
            mean=_number(data["glucose_mean"]),
            min=_number(data["glucose_min"]),
            max=_number(data["glucose_max"]),
            unit=data["unit"],
            low_alarms=data["low_alarms"],
        )

    async def _async_stats(self, start: datetime, end: datetime) -> ReportStats | None:
        """Return the statistics of the glucose history of a period."""
        if "recorder" not in self.hass.config.components:
            _LOGGER.debug("No recorder, report without statistics")
            return None
        # Imported here: the recorder is optional.
        from homeassistant.components.recorder import (
            get_instance,
            history,
        )

        glucose = self.monitor.source.entities.glucose
        states = await get_instance(self.hass).async_add_executor_job(
            history.state_changes_during_period,
            self.hass,
            # A change exactly at the start counts neither as state at the
            # start time nor as change in the period; compute_stats clips.
            start - timedelta(seconds=1),
            end,
            glucose,
        )
        manual_unit = self.monitor.source.entities.unit
        samples = [
            (
                state.last_changed,
                to_mg_dl(
                    parse_number(state_value(state)),
                    state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) or manual_unit,
                ),
            )
            for state in states.get(glucose, [])
        ]
        low, high = self.monitor.range_thresholds()
        return compute_stats(samples, start, end, low, high)


def _number(value: float | None) -> str:
    if value is None:
        return "–"
    return f"{value:g}"


def _parse(value: object) -> datetime | None:
    return dt_util.parse_datetime(value) if isinstance(value, str) else None
