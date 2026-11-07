"""Run the alarms of one monitored person.

Connects the alarm state machines (``alarm.py``) to Home Assistant: reads the
glucose data and threshold entities, schedules the time based checks, fires
the events of the device triggers (``device_trigger.py``) and keeps the alarm
states across restarts.

Every config entry has its own monitor. Alarms of different entries, and
different alarms of one entry, are acknowledged and snoozed independently.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_HOME, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_state_change_event,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util import dt as dt_util

from .alarm import AlarmEngine, AlarmSettings, AlarmState, AlarmStatus, Condition, Phase
from .const import (
    ALARM_DATA_LOSS,
    ALARM_DEFAULTS,
    ALARMS,
    CONF_CLEAR_OFFSET,
    CONF_DELAY,
    CONF_DURATION,
    CONF_ENABLED,
    CONF_MAX_AGE,
    CONF_ONLY_WHEN_HOME,
    CONF_PAUSE,
    CONF_PERSON_ENTITY,
    CONF_REPEAT,
    CONF_SNOOZE,
    CONF_THRESHOLD_ENTITY,
    DEFAULT_PAUSE_DURATION,
    DOMAIN,
    EVENT_ALARM,
    EVENT_MOBILE_APP_NOTIFICATION_ACTION,
    PAUSABLE_ALARMS,
    THRESHOLD_ALARMS,
    TRIGGER_ALERT,
    TRIGGER_ENDED,
)
from .glucose import GlucoseReading
from .source import (
    MG_DL,
    GlucoseSource,
    from_mg_dl,
    sensor_unit,
    to_mg_dl,
    value_mg_dl,
)

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
# Phases of the alert trigger; the others are the ended trigger.
ALERT_PHASES = (Phase.TRIGGERED, Phase.REPEAT)
TEXT_PREFIX = f"component.{DOMAIN}.selector.alarm_text.options."

type AlarmEventListener = Callable[[str, Phase, dict[str, Any]], None]


def minutes(value: float) -> timedelta:
    """Return a duration from minutes."""
    return timedelta(minutes=float(value))


def alarm_options(options: Mapping[str, Any], alarm: str) -> dict[str, Any]:
    """Return the options of an alarm, completed with the defaults."""
    return {**ALARM_DEFAULTS[alarm], **options.get(alarm, {})}


def enabled_alarms(options: Mapping[str, Any]) -> list[str]:
    """Return the enabled alarms."""
    return [alarm for alarm in ALARMS if options.get(alarm, {}).get(CONF_ENABLED)]


def alarm_settings(alarm: str, options: Mapping[str, Any]) -> AlarmSettings:
    """Return the timing of an alarm from its options."""
    return AlarmSettings(
        delay=minutes(options.get(CONF_DELAY, 0)),
        repeat=minutes(options[CONF_REPEAT]) if options.get(CONF_REPEAT) else None,
        snooze=minutes(options[CONF_SNOOZE]),
    )


def notification_tag(entry_id: str, alarm: str) -> str:
    """Return the notification tag of an alarm, unique per entry."""
    return f"{DOMAIN}_{entry_id}_{alarm}"


def acknowledge_action(entry_id: str, alarm: str) -> str:
    """Return the mobile app notification action that acknowledges an alarm."""
    return f"{DOMAIN.upper()}_ACK_{entry_id}_{alarm}"


def no_reading_time_issue(entry_id: str) -> str:
    """Return the repair issue ID for a source without reading time."""
    return f"no_reading_time_{entry_id}"


class AlarmMonitor:
    """Run the enabled alarms of one config entry."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, source: GlucoseSource
    ) -> None:
        """Initialize."""
        self.hass = hass
        self.entry = entry
        self.source = source
        options = entry.options
        self._options = {alarm: alarm_options(options, alarm) for alarm in ALARMS}
        self.alarms = enabled_alarms(options)
        self.engines = {
            alarm: AlarmEngine(alarm_settings(alarm, self._options[alarm]))
            for alarm in self.alarms
        }
        # Readings older than this are stale; also the data loss limit.
        self.max_age = minutes(self._options[ALARM_DATA_LOSS][CONF_MAX_AGE])
        self.pause_duration = minutes(
            options.get(CONF_PAUSE, {}).get(CONF_DURATION, DEFAULT_PAUSE_DURATION)
        )
        self.pause_until: datetime | None = None
        self.last_reading_time: datetime | None = None
        self._store = Store[dict[str, Any]](
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._texts: dict[str, str] = {}
        self._listeners: list[CALLBACK_TYPE] = []
        self._event_listeners: list[AlarmEventListener] = []
        self._cancel_timer: CALLBACK_TYPE | None = None
        self._issue = False
        # After a (re)start the source gets max_age to deliver data.
        self._started = dt_util.utcnow()

    @property
    def reading_time_known(self) -> bool:
        """Return True once the source has provided a reading time.

        Without a reading time the age of the data is unknown: no alarms.
        """
        return self.last_reading_time is not None

    @property
    def paused(self) -> bool:
        """Return True while the pausable alarms are paused."""
        return self.pause_until is not None and dt_util.utcnow() < self.pause_until

    def state(self, alarm: str) -> AlarmState:
        """Return the state of an enabled alarm."""
        return self.engines[alarm].state

    async def async_start(self) -> None:
        """Restore the states and start tracking."""
        self._started = dt_util.utcnow()
        await self._async_restore()
        self._texts = await async_get_translations(
            self.hass, self.hass.config.language, "selector", [DOMAIN]
        )
        entry = self.entry
        entry.async_on_unload(self.source.async_add_listener(self._async_update))
        tracked = [
            entity_id
            for alarm in self.alarms
            if alarm in THRESHOLD_ALARMS
            and (entity_id := self._options[alarm].get(CONF_THRESHOLD_ENTITY))
        ]
        if person := entry.options.get(CONF_PERSON_ENTITY):
            tracked.append(person)
        if tracked:
            entry.async_on_unload(
                async_track_state_change_event(
                    self.hass, tracked, self._async_state_changed
                )
            )
        entry.async_on_unload(
            self.hass.bus.async_listen(
                EVENT_MOBILE_APP_NOTIFICATION_ACTION, self._async_mobile_action
            )
        )
        entry.async_on_unload(self._async_cancel_timer)
        self._async_update()

    async def async_stop(self) -> None:
        """Write the alarm states before unloading."""
        await self._store.async_save(self._data_to_store())

    async def async_remove(self) -> None:
        """Remove the stored state and the repair issue of a deleted entry."""
        await self._store.async_remove()
        ir.async_delete_issue(
            self.hass, DOMAIN, no_reading_time_issue(self.entry.entry_id)
        )

    @callback
    def async_add_listener(self, update_callback: CALLBACK_TYPE) -> CALLBACK_TYPE:
        """Call ``update_callback`` after every update."""
        self._listeners.append(update_callback)
        return lambda: self._listeners.remove(update_callback)

    @callback
    def async_add_event_listener(self, listener: AlarmEventListener) -> CALLBACK_TYPE:
        """Call ``listener(alarm, phase, variables)`` for every alarm event."""
        self._event_listeners.append(listener)
        return lambda: self._event_listeners.remove(listener)

    @callback
    def async_acknowledge(self, alarm: str | None = None) -> None:
        """Acknowledge one alarm, or all alarms of this entry."""
        now = dt_util.utcnow()
        for name in [alarm] if alarm else list(self.engines):
            if (engine := self.engines.get(name)) is not None:
                self._async_notify_all(name, engine.acknowledge(now), now)
        self._async_update()

    @callback
    def async_pause(self, on: bool) -> None:
        """Pause or resume the pausable alarms (never urgent low)."""
        now = dt_util.utcnow()
        pausable = [alarm for alarm in PAUSABLE_ALARMS if alarm in self.engines]
        if on:
            self.pause_until = now + self.pause_duration
            for alarm in pausable:
                phases = self.engines[alarm].acknowledge(now, until=self.pause_until)
                self._async_notify_all(alarm, phases, now)
        else:
            self.pause_until = None
            # Check again at once, as when the pause ends by itself.
            for alarm in pausable:
                status = self.engines[alarm].status
                if status.state is AlarmState.SNOOZED and (
                    status.snoozed_until is None or status.snoozed_until > now
                ):
                    status.snoozed_until = now
        self._async_update()

    @callback
    def _async_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Check the alarms when a threshold or the person changes."""
        self._async_update()

    @callback
    def _async_mobile_action(self, event: Event) -> None:
        """Acknowledge an alarm from a mobile app notification action."""
        action = event.data.get("action")
        for alarm in self.engines:
            if action == acknowledge_action(self.entry.entry_id, alarm):
                self.async_acknowledge(alarm)

    @callback
    def _async_timer(self, now: datetime) -> None:
        """Check the alarms at a scheduled time."""
        self._cancel_timer = None
        self._async_update()

    @callback
    def _async_update(self) -> None:
        """Check all alarms and notify the listeners."""
        now = dt_util.utcnow()
        reading = self.source.reading
        if reading.reading_time is not None and (
            self.last_reading_time is None
            or reading.reading_time > self.last_reading_time
        ):
            self.last_reading_time = reading.reading_time
        if self.pause_until is not None and now >= self.pause_until:
            self.pause_until = None
        self._async_update_issue(reading)

        if self.reading_time_known:
            for alarm, engine in self.engines.items():
                phases = engine.update(
                    now, self._condition(alarm, reading, now), self._may_start(alarm)
                )
                self._async_notify_all(alarm, phases, now)

        self._async_schedule(now)
        self._store.async_delay_save(self._data_to_store, 1)
        for update_callback in list(self._listeners):
            update_callback()

    def _condition(
        self, alarm: str, reading: GlucoseReading, now: datetime
    ) -> Condition:
        """Return where the current data is for an alarm."""
        assert self.last_reading_time is not None
        too_old = now - self.last_reading_time > self.max_age
        if alarm == ALARM_DATA_LOSS:
            if not too_old:
                return Condition.CLEAR
            # Right after a restart the source may not be loaded yet.
            if now - self._started <= self.max_age:
                return Condition.UNKNOWN
            return Condition.ALARM
        options = self._options[alarm]
        if (
            reading.value is None
            or too_old
            or not (entity_id := options.get(CONF_THRESHOLD_ENTITY))
            or (
                threshold := value_mg_dl(
                    self.hass, entity_id, self.source.entities.unit
                )
            )
            is None
        ):
            return Condition.UNKNOWN
        if reading.value < threshold:
            return Condition.ALARM
        offset = to_mg_dl(float(options.get(CONF_CLEAR_OFFSET) or 0), self._unit()) or 0
        if reading.value >= threshold + offset:
            return Condition.CLEAR
        return Condition.BETWEEN

    def _may_start(self, alarm: str) -> bool:
        """Return True if a new alarm may start now."""
        if alarm in PAUSABLE_ALARMS and self.paused:
            return False
        if self._options[alarm].get(CONF_ONLY_WHEN_HOME) and (
            person := self.entry.options.get(CONF_PERSON_ENTITY)
        ):
            state = self.hass.states.get(person)
            # Unknown presence does not suppress alarms.
            return state is None or state.state in (
                STATE_HOME,
                STATE_UNKNOWN,
                STATE_UNAVAILABLE,
            )
        return True

    def _unit(self) -> str:
        """Return the unit of the glucose data."""
        sources = self.source.entities
        return sensor_unit(self.hass, sources.glucose) or sources.unit or MG_DL

    @callback
    def _async_schedule(self, now: datetime) -> None:
        """Schedule the next time based check."""
        self._async_cancel_timer()
        times = [engine.next_check() for engine in self.engines.values()]
        if self.last_reading_time is not None:
            # The data becomes stale strictly after max_age.
            times.append(self.last_reading_time + self.max_age + timedelta(seconds=1))
        times.append(self.pause_until)
        times.append(self._started + self.max_age + timedelta(seconds=1))
        # Times in the past wait for new data instead (e.g. a snooze that
        # ended without usable data).
        if future := [time for time in times if time is not None and time > now]:
            self._cancel_timer = async_track_point_in_utc_time(
                self.hass, self._async_timer, min(future)
            )

    @callback
    def _async_cancel_timer(self) -> None:
        if self._cancel_timer is not None:
            self._cancel_timer()
            self._cancel_timer = None

    @callback
    def _async_update_issue(self, reading: GlucoseReading) -> None:
        """Tell the user when the source provides no reading time."""
        missing = (
            bool(self.alarms)
            and not self.reading_time_known
            and reading.value is not None
        )
        if missing == self._issue:
            return
        self._issue = missing
        issue_id = no_reading_time_issue(self.entry.entry_id)
        if missing:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="no_reading_time",
                translation_placeholders={"name": self.entry.title},
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    @callback
    def _async_notify_all(self, alarm: str, phases: list[Phase], now: datetime) -> None:
        for phase in phases:
            self._async_notify(alarm, phase, now)

    @callback
    def _async_notify(self, alarm: str, phase: Phase, now: datetime) -> None:
        """Tell the event listeners and fire the event of the device triggers."""
        variables = self._variables(alarm, phase, now)
        _LOGGER.debug("%s: %s alarm %s", self.entry.title, alarm, phase)
        for listener in list(self._event_listeners):
            listener(alarm, phase, variables)
        kind = TRIGGER_ALERT if phase in ALERT_PHASES else TRIGGER_ENDED
        entry_id = self.entry.entry_id
        device = dr.async_get(self.hass).async_get_device_by_identifier(
            (DOMAIN, entry_id), entry_id
        )
        self.hass.bus.async_fire(
            EVENT_ALARM,
            {
                "device_id": None if device is None else device.id,
                "type": f"{alarm}_{kind}",
                **variables,
            },
        )

    def _variables(self, alarm: str, phase: Phase, now: datetime) -> dict[str, Any]:
        """Return the data of an alarm event."""
        reading = self.source.reading
        unit = self._unit()
        digits = 0 if unit == MG_DL else 1
        glucose = from_mg_dl(reading.value, unit)
        change = from_mg_dl(reading.change, unit)
        glucose = None if glucose is None else round(glucose, digits)
        change = None if change is None else round(change, digits)
        age = (
            None
            if self.last_reading_time is None
            else int((now - self.last_reading_time).total_seconds() // 60)
        )
        name = self.entry.title
        if phase is Phase.ACKNOWLEDGED or phase is Phase.RESOLVED:
            message = self._text(phase.value)
        elif alarm == ALARM_DATA_LOSS:
            message = self._text("data_loss_message", minutes=age)
        else:
            message = " ".join(
                part
                for part in (_format(glucose, digits), unit, reading.trend_arrow)
                if part
            )
        return {
            "entry_id": self.entry.entry_id,
            "person_name": name,
            "alarm": alarm,
            "phase": phase.value,
            "glucose": glucose,
            "unit": unit,
            "trend": None if reading.trend is None else reading.trend.value,
            "trend_arrow": reading.trend_arrow,
            "delta": change,
            "data_age_min": age,
            "title": self._text(alarm, name=name),
            "message": message,
            "tag": notification_tag(self.entry.entry_id, alarm),
            "ack_action": acknowledge_action(self.entry.entry_id, alarm),
        }

    def _text(self, key: str, **placeholders: Any) -> str:
        """Return a translated text."""
        text = self._texts.get(TEXT_PREFIX + key, key)
        try:
            return text.format(**placeholders)
        except KeyError, IndexError, ValueError:
            return text

    async def _async_restore(self) -> None:
        """Restore the alarm states after a restart."""
        data = await self._store.async_load() or {}
        for alarm, status in data.get("alarms", {}).items():
            if (engine := self.engines.get(alarm)) is not None:
                engine.status = AlarmStatus.from_dict(status)
        self.last_reading_time = _parse_time(data.get("last_reading_time"))
        self.pause_until = _parse_time(data.get("pause_until"))

    def _data_to_store(self) -> dict[str, Any]:
        return {
            "alarms": {
                alarm: engine.status.as_dict() for alarm, engine in self.engines.items()
            },
            "last_reading_time": _iso(self.last_reading_time),
            "pause_until": _iso(self.pause_until),
        }


def _format(value: float | None, digits: int) -> str:
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    return dt_util.parse_datetime(value)
