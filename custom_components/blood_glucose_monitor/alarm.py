"""State machine of one alarm.

This module has no Home Assistant dependencies so the alarm behavior can be
unit tested in isolation. The caller decides whether the current data is in
the alarm range (see ``Condition``) and whether a new alarm may start; this
module only tracks the state over time.

States::

    idle ──alarm──▶ pending ──delay over──▶ active ──clear──▶ idle
                       │                     │  ▲
                       └──not alarm──▶ idle  │  └──repeat
                                             ▼
                                          snoozed ──snooze over──▶ re-check

A snoozed alarm is checked again when the snooze ends: if the data is still
in the alarm range, the alarm starts again at once. ``snooze`` passes the
snooze of an acknowledged urgent alarm on to the plain one (urgent low to
low), even when that one is idle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any


class AlarmState(StrEnum):
    """State of an alarm."""

    IDLE = "idle"
    PENDING = "pending"
    ACTIVE = "active"
    SNOOZED = "snoozed"


class Phase(StrEnum):
    """What happened to an alarm, passed to the user's actions."""

    TRIGGERED = "triggered"
    REPEAT = "repeat"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class Condition(StrEnum):
    """Where the current data is, as seen by one alarm."""

    ALARM = "alarm"
    """In the alarm range, e.g. below the low threshold."""

    BETWEEN = "between"
    """Out of the alarm range, but not yet clear (hysteresis)."""

    CLEAR = "clear"
    """Clearly out of the alarm range: ends an active or snoozed alarm."""

    UNKNOWN = "unknown"
    """No usable data (missing or stale): nothing starts or ends."""


@dataclass(frozen=True, slots=True)
class AlarmSettings:
    """Timing of one alarm."""

    delay: timedelta = timedelta(0)
    """How long the data has to stay in the alarm range before the alarm."""

    repeat: timedelta | None = None
    """Repeat interval of an active alarm, ``None`` to notify only once."""

    snooze: timedelta = timedelta(minutes=15)
    """How long an acknowledged alarm stays silent."""


@dataclass(slots=True)
class AlarmStatus:
    """Persistent state of one alarm."""

    state: AlarmState = AlarmState.IDLE
    since: datetime | None = None
    """When the current state started (pending or active)."""

    notified: datetime | None = None
    """Last notification of an active alarm."""

    snoozed_until: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON serializable dict."""
        return {
            "state": self.state.value,
            "since": _iso(self.since),
            "notified": _iso(self.notified),
            "snoozed_until": _iso(self.snoozed_until),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AlarmStatus:
        """Restore from ``as_dict`` output, idle if the data is invalid."""
        try:
            return cls(
                state=AlarmState(data["state"]),
                since=_parse(data.get("since")),
                notified=_parse(data.get("notified")),
                snoozed_until=_parse(data.get("snoozed_until")),
            )
        except KeyError, TypeError, ValueError:
            return cls()


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _parse(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


class AlarmEngine:
    """Track one alarm over time."""

    def __init__(
        self, settings: AlarmSettings, status: AlarmStatus | None = None
    ) -> None:
        """Initialize."""
        self.settings = settings
        self.status = status or AlarmStatus()

    @property
    def state(self) -> AlarmState:
        """Return the current state."""
        return self.status.state

    def update(
        self, now: datetime, condition: Condition, may_start: bool
    ) -> list[Phase]:
        """Update the state, return what happened.

        ``may_start`` is False while a new alarm must not start (e.g. paused
        or the person is away). It does not end an active alarm.
        """
        status = self.status
        if status.state is AlarmState.IDLE:
            if condition is not Condition.ALARM or not may_start:
                return []
            self._set(AlarmState.PENDING, now)

        if status.state is AlarmState.PENDING:
            if condition is Condition.UNKNOWN:
                return []
            if condition is not Condition.ALARM or not may_start:
                self._set(AlarmState.IDLE)
                return []
            assert status.since is not None
            if now - status.since < self.settings.delay:
                return []
            return self._activate(now)

        if condition is Condition.CLEAR:
            # Snoozed without ever being on (see ``snooze``): ends quietly.
            silent = status.state is AlarmState.SNOOZED and status.since is None
            self._set(AlarmState.IDLE)
            return [] if silent else [Phase.RESOLVED]

        if status.state is AlarmState.ACTIVE:
            repeat = self.settings.repeat
            assert status.notified is not None
            if repeat and now - status.notified >= repeat:
                status.notified = now
                return [Phase.REPEAT]
            return []

        # Snoozed: check again once the snooze is over.
        assert status.snoozed_until is not None
        if now < status.snoozed_until or condition is Condition.UNKNOWN:
            return []
        if condition is Condition.ALARM and may_start:
            return self._activate(now)
        self._set(AlarmState.IDLE)
        return []

    def acknowledge(self, now: datetime, until: datetime | None = None) -> list[Phase]:
        """Acknowledge the alarm: silent until the snooze (or ``until``) ends."""
        if self.status.state not in (AlarmState.PENDING, AlarmState.ACTIVE):
            return []
        was_active = self.status.state is AlarmState.ACTIVE
        self._set(AlarmState.SNOOZED, now)
        self.status.snoozed_until = until or now + self.settings.snooze
        return [Phase.ACKNOWLEDGED] if was_active else []

    def snooze(self, now: datetime, until: datetime) -> list[Phase]:
        """Take over the snooze of an acknowledged urgent alarm until ``until``.

        A pending or active alarm is acknowledged, an idle one is held (no
        alarm starts before ``until``), a snoozed one stays snoozed at least
        until ``until``.
        """
        status = self.status
        match status.state:
            case AlarmState.PENDING | AlarmState.ACTIVE:
                return self.acknowledge(now, until)
            case AlarmState.IDLE:
                self._set(AlarmState.SNOOZED)
                status.snoozed_until = until
            case AlarmState.SNOOZED:
                assert status.snoozed_until is not None
                status.snoozed_until = max(status.snoozed_until, until)
        return []

    def next_check(self) -> datetime | None:
        """Return when the state may change without new data."""
        status = self.status
        match status.state:
            case AlarmState.PENDING:
                assert status.since is not None
                return status.since + self.settings.delay
            case AlarmState.ACTIVE if self.settings.repeat:
                assert status.notified is not None
                return status.notified + self.settings.repeat
            case AlarmState.SNOOZED:
                return status.snoozed_until
        return None

    def _activate(self, now: datetime) -> list[Phase]:
        self._set(AlarmState.ACTIVE, now)
        self.status.notified = now
        return [Phase.TRIGGERED]

    def _set(self, state: AlarmState, now: datetime | None = None) -> None:
        status = self.status
        status.state = state
        status.since = now
        status.notified = None
        status.snoozed_until = None
