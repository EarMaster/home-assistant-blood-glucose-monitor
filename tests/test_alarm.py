"""Tests for the dependency-free alarm state machine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.blood_glucose_monitor.alarm import (
    AlarmEngine,
    AlarmSettings,
    AlarmState,
    AlarmStatus,
    Condition,
    Phase,
)

T0 = datetime(2026, 11, 7, 22, 0, tzinfo=UTC)
SETTINGS = AlarmSettings(
    delay=timedelta(minutes=5),
    repeat=timedelta(minutes=5),
    snooze=timedelta(minutes=15),
)
ALARM = Condition.ALARM
BETWEEN = Condition.BETWEEN
CLEAR = Condition.CLEAR
UNKNOWN = Condition.UNKNOWN


def at(minutes: float) -> datetime:
    """Return T0 plus minutes."""
    return T0 + timedelta(minutes=minutes)


def active_engine() -> AlarmEngine:
    """Return an engine with an alarm that became active at minute 5."""
    engine = AlarmEngine(SETTINGS)
    engine.update(at(0), ALARM, True)
    assert engine.update(at(5), ALARM, True) == [Phase.TRIGGERED]
    return engine


def test_short_dip_gives_no_alarm() -> None:
    """Leaving the alarm range before the delay ends cancels the alarm."""
    engine = AlarmEngine(SETTINGS)
    assert engine.update(at(0), ALARM, True) == []
    assert engine.state is AlarmState.PENDING
    assert engine.next_check() == at(5)
    assert engine.update(at(3), BETWEEN, True) == []
    assert engine.state is AlarmState.IDLE
    assert engine.next_check() is None


def test_alarm_after_delay_and_repeat() -> None:
    """An alarm starts after the delay and repeats until it clears."""
    engine = active_engine()
    assert engine.next_check() == at(10)
    assert engine.update(at(7), ALARM, True) == []
    assert engine.update(at(10), BETWEEN, True) == [Phase.REPEAT]
    assert engine.update(at(15), ALARM, True) == [Phase.REPEAT]
    assert engine.update(at(16), CLEAR, True) == [Phase.RESOLVED]
    assert engine.state is AlarmState.IDLE


def test_no_delay_and_no_repeat() -> None:
    """Without delay the alarm starts at once; without repeat it stays quiet."""
    engine = AlarmEngine(AlarmSettings())
    assert engine.update(at(0), ALARM, True) == [Phase.TRIGGERED]
    assert engine.next_check() is None
    assert engine.update(at(60), ALARM, True) == []


def test_unknown_data_holds_the_state() -> None:
    """Missing or stale data neither starts, advances nor ends an alarm."""
    engine = AlarmEngine(SETTINGS)
    engine.update(at(0), ALARM, True)
    assert engine.update(at(6), UNKNOWN, True) == []
    assert engine.state is AlarmState.PENDING
    assert engine.update(at(7), ALARM, True) == [Phase.TRIGGERED]
    assert engine.update(at(9), UNKNOWN, True) == []
    assert engine.state is AlarmState.ACTIVE
    assert engine.update(at(12), UNKNOWN, True) == [Phase.REPEAT]


def test_acknowledge_snoozes_and_rechecks() -> None:
    """After the snooze, an alarm that is still low starts again at once."""
    engine = active_engine()
    assert engine.acknowledge(at(6)) == [Phase.ACKNOWLEDGED]
    assert engine.state is AlarmState.SNOOZED
    assert engine.next_check() == at(21)
    assert engine.update(at(10), ALARM, True) == []
    assert engine.update(at(21), ALARM, True) == [Phase.TRIGGERED]
    assert engine.state is AlarmState.ACTIVE


def test_snooze_ends_quietly_when_no_longer_low() -> None:
    """A snooze that ends between the thresholds just ends the alarm."""
    engine = active_engine()
    engine.acknowledge(at(6))
    assert engine.update(at(21), BETWEEN, True) == []
    assert engine.state is AlarmState.IDLE


def test_snooze_waits_for_known_data() -> None:
    """A snooze ending without usable data is checked again later."""
    engine = active_engine()
    engine.acknowledge(at(6))
    assert engine.update(at(21), UNKNOWN, True) == []
    assert engine.state is AlarmState.SNOOZED
    assert engine.update(at(23), ALARM, True) == [Phase.TRIGGERED]


def test_clear_during_snooze_resolves() -> None:
    """Recovering during the snooze resolves the alarm."""
    engine = active_engine()
    engine.acknowledge(at(6))
    assert engine.update(at(10), CLEAR, True) == [Phase.RESOLVED]
    assert engine.state is AlarmState.IDLE


def test_acknowledge_until() -> None:
    """A pause acknowledges until the given time."""
    engine = active_engine()
    assert engine.acknowledge(at(6), until=at(66)) == [Phase.ACKNOWLEDGED]
    assert engine.next_check() == at(66)
    # Still paused when the snooze ends: no new alarm.
    assert engine.update(at(66), ALARM, False) == []
    assert engine.state is AlarmState.IDLE


@pytest.mark.parametrize("state", [AlarmState.IDLE, AlarmState.SNOOZED])
def test_acknowledge_without_active_alarm(state: AlarmState) -> None:
    """Acknowledging an idle or snoozed alarm does nothing."""
    engine = AlarmEngine(
        SETTINGS, AlarmStatus(state=state, since=T0, snoozed_until=at(15))
    )
    assert engine.acknowledge(at(1)) == []
    assert engine.status.state is state


def test_acknowledge_pending_alarm_is_silent() -> None:
    """Acknowledging a pending alarm snoozes it without notification."""
    engine = AlarmEngine(SETTINGS)
    engine.update(at(0), ALARM, True)
    assert engine.acknowledge(at(1)) == []
    assert engine.state is AlarmState.SNOOZED


def test_snooze_active_alarm_acknowledges() -> None:
    """Taking over a snooze acknowledges an active alarm until that time."""
    engine = active_engine()
    assert engine.snooze(at(6), at(16)) == [Phase.ACKNOWLEDGED]
    assert engine.next_check() == at(16)


def test_snooze_holds_idle_alarm() -> None:
    """An idle alarm does not start before the snooze ends, then re-checks."""
    engine = AlarmEngine(SETTINGS)
    assert engine.snooze(at(0), at(10)) == []
    assert engine.state is AlarmState.SNOOZED
    assert engine.update(at(5), ALARM, True) == []
    assert engine.update(at(10), ALARM, True) == [Phase.TRIGGERED]


def test_snooze_of_idle_alarm_ends_quietly() -> None:
    """A held alarm that never sounded ends without "resolved"."""
    engine = AlarmEngine(SETTINGS)
    engine.snooze(at(0), at(10))
    assert engine.update(at(5), CLEAR, True) == []
    assert engine.state is AlarmState.IDLE


def test_snooze_keeps_longer_snooze() -> None:
    """A longer running snooze (e.g. the pause) is not shortened."""
    engine = active_engine()
    engine.acknowledge(at(6), until=at(66))
    assert engine.snooze(at(7), at(17)) == []
    assert engine.next_check() == at(66)
    engine.snooze(at(8), at(80))
    assert engine.next_check() == at(80)


def test_may_start() -> None:
    """A new alarm cannot start while not allowed; an active one continues."""
    engine = AlarmEngine(SETTINGS)
    assert engine.update(at(0), ALARM, False) == []
    assert engine.state is AlarmState.IDLE
    engine.update(at(1), ALARM, True)
    assert engine.update(at(2), ALARM, False) == []
    assert engine.state is AlarmState.IDLE

    engine = active_engine()
    assert engine.update(at(10), ALARM, False) == [Phase.REPEAT]
    assert engine.update(at(11), CLEAR, False) == [Phase.RESOLVED]


def test_status_round_trip() -> None:
    """The status survives a restart."""
    engine = active_engine()
    engine.acknowledge(at(6))
    restored = AlarmStatus.from_dict(engine.status.as_dict())
    assert restored == engine.status
    assert AlarmStatus.from_dict(AlarmStatus().as_dict()) == AlarmStatus()


@pytest.mark.parametrize(
    "data", [{}, {"state": "exploded"}, {"state": "active", "since": "yesterday"}]
)
def test_invalid_status_is_idle(data: dict[str, str]) -> None:
    """Invalid stored data restores an idle alarm."""
    assert AlarmStatus.from_dict(data) == AlarmStatus()
