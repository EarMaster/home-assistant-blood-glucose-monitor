"""Run the alarms of one monitored person.

Connects the alarm state machines (``alarm.py``) to Home Assistant: reads the
glucose data and threshold entities, schedules the time based checks, fires
the events of the event entities (``event.py``) and keeps the alarm
states across restarts.

Every config entry has its own monitor. Alarms of different entries, and
different alarms of one entry, are acknowledged and snoozed independently.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, time as dt_time, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    STATE_HOME,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_state_change_event,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util import dt as dt_util

from .alarm import AlarmEngine, AlarmSettings, AlarmState, AlarmStatus, Condition, Phase
from .const import (
    ALARM_CHARGING,
    ALARM_DATA_LOSS,
    ALARM_DEFAULTS,
    ALARM_HIGH,
    ALARM_ICONS,
    ALARM_LOW,
    ALARM_RAPID_FALL,
    ALARM_RAPID_RISE,
    ALARM_URGENT_HIGH,
    ALARM_URGENT_LOW,
    ALARMS,
    CHANGE_ALARMS,
    CHARGING_STATES,
    CONF_BATTERY_ENTITY,
    CONF_BATTERY_LIMIT,
    CONF_BATTERY_LIMIT_ENTITY,
    CONF_CHARGING_ENTITY,
    CONF_CLEAR_OFFSET,
    CONF_DELAY,
    CONF_DETECTION,
    CONF_DUE_TIME,
    CONF_DURATION,
    CONF_LAST_CHANGE_ENTITY,
    CONF_MAX_AGE,
    CONF_ONLY_WHEN_HOME,
    CONF_PAUSE,
    CONF_PERSON_ENTITY,
    CONF_RATE_ENTITY,
    CONF_RATE_LIMIT,
    CONF_REMINDER_TIME,
    CONF_REPEAT,
    CONF_REPORT,
    CONF_REPORT_ENTITY,
    CONF_SNOOZE,
    CONF_THRESHOLD,
    CONF_THRESHOLD_ENTITY,
    CONF_TIME_ENTITY,
    CONF_TREND_LEVEL,
    CONF_WARNING,
    CONF_WEAR_DURATION,
    CONF_WEAR_DURATION_ENTITY,
    DEFAULT_PAUSE_DURATION,
    DETECTION_OFF,
    DETECTION_TREND,
    DOMAIN,
    DURATION_UNITS,
    EVENT_MOBILE_APP_NOTIFICATION_ACTION,
    HIGH_ALARMS,
    LOW_ALARMS,
    MAX_RATE_GAP_MINUTES,
    NOT_CHARGING_STATES,
    PAUSABLE_ALARMS,
    RATE_ALARMS,
    RATE_UNITS,
    TREND_LEVEL_VERY_QUICKLY,
    TRIGGER_ALERT,
    TRIGGER_ENDED,
    TRIGGER_SOON,
)
from .glucose import GlucoseReading, Trend, parse_number
from .reports import ReportTracker
from .source import (
    MG_DL,
    GlucoseSource,
    from_mg_dl,
    sensor_unit,
    state_value,
    to_mg_dl,
    value_mg_dl,
)

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
# Phases of the alert event; the others are the ended event.
ALERT_PHASES = (Phase.TRIGGERED, Phase.REPEAT)
TEXT_PREFIX = f"component.{DOMAIN}.selector.alarm_text.options."

type EventListener = Callable[[str, dict[str, Any]], None]

STATUS_OK = "ok"
STATUS_PAUSED = "paused"
STATUS_NO_DATA = "no_data"
# Overall status, most important first: the first that applies wins.
STATUS_ALARMS = (
    ALARM_URGENT_LOW,
    ALARM_LOW,
    ALARM_RAPID_FALL,
    ALARM_URGENT_HIGH,
    ALARM_HIGH,
    ALARM_RAPID_RISE,
)
STATUSES = (STATUS_NO_DATA, *STATUS_ALARMS, STATUS_PAUSED, STATUS_OK)

# Trends that count as a fast change, per alarm and trend level.
FAST_TRENDS = {
    ALARM_RAPID_FALL: (Trend.FALLING_VERY_QUICKLY, Trend.FALLING_QUICKLY),
    ALARM_RAPID_RISE: (Trend.RISING_VERY_QUICKLY, Trend.RISING_QUICKLY),
}
# A value arriving this long after its reading time still belongs to it.
RATE_VALUE_WINDOW = timedelta(seconds=30)
# Trends that tell nothing about the change.
UNKNOWN_TRENDS = (Trend.NOT_COMPUTABLE, Trend.RATE_OUT_OF_RANGE)
# Alarm states that count for the overall status.
RUNNING_STATES = (AlarmState.ACTIVE, AlarmState.SNOOZED)


def minutes(value: float) -> timedelta:
    """Return a duration from minutes."""
    return timedelta(minutes=float(value))


def alarm_options(options: Mapping[str, Any], alarm: str) -> dict[str, Any]:
    """Return the options of an alarm, completed with the defaults."""
    return {**ALARM_DEFAULTS[alarm], **options.get(alarm, {})}


def enabled_alarms(options: Mapping[str, Any]) -> list[str]:
    """Return the active alarms.

    A threshold alarm is active once it has a threshold (number or entity), a rapid
    change alarm once a detection is selected, a change reminder once it has
    a wear duration; the data loss alarm is always active. Notifications are
    the user's automations.
    """
    return [
        alarm
        for alarm in ALARMS
        if alarm == ALARM_DATA_LOSS
        or options.get(alarm, {}).get(CONF_THRESHOLD_ENTITY)
        or options.get(alarm, {}).get(CONF_THRESHOLD) is not None
        or options.get(alarm, {}).get(CONF_DETECTION, DETECTION_OFF) != DETECTION_OFF
        or (
            alarm == ALARM_CHARGING
            and options.get(alarm, {}).get(CONF_BATTERY_ENTITY)
            and options.get(alarm, {}).get(CONF_CHARGING_ENTITY)
        )
        or (
            alarm in CHANGE_ALARMS
            and (
                options.get(alarm, {}).get(CONF_WEAR_DURATION_ENTITY)
                or duration(options.get(alarm, {}).get(CONF_WEAR_DURATION))
            )
        )
    ]


def warning_alarms(options: Mapping[str, Any]) -> list[str]:
    """Return the enabled change reminders with a warning before."""
    return [
        alarm
        for alarm in enabled_alarms(options)
        if alarm in CHANGE_ALARMS and duration(options[alarm].get(CONF_WARNING))
    ]


def duration(value: object) -> timedelta | None:
    """Return a positive duration from a duration selector value."""
    if not isinstance(value, Mapping):
        return None
    try:
        delta = timedelta(
            **{
                key: float(value[key])
                for key in ("days", "hours", "minutes", "seconds")
                if value.get(key)
            }
        )
    except TypeError, ValueError:
        return None
    return delta if delta > timedelta(0) else None


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
        # Latest and previous (time, mg/dL) for the own rate of change.
        self._latest: tuple[datetime, float] | None = None
        self._previous: tuple[datetime, float] | None = None
        self._latest_at = dt_util.utcnow()
        self._store = Store[dict[str, Any]](
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._texts: dict[str, str] = {}
        self._listeners: list[CALLBACK_TYPE] = []
        self._event_listeners: list[EventListener] = []
        self._cancel_timer: CALLBACK_TYPE | None = None
        self._issue = False
        # After a (re)start the source gets max_age to deliver data.
        self._started = dt_util.utcnow()
        report_entity = options.get(CONF_REPORT, {}).get(CONF_REPORT_ENTITY)
        self.report = (
            None
            if not report_entity
            else ReportTracker(
                self,
                report_entity,
                only_when_home=bool(
                    options.get(CONF_REPORT, {}).get(CONF_ONLY_WHEN_HOME)
                ),
            )
        )
        # Changes recorded by the integration, and the due time per change
        # reminder whose warning was sent.
        self.changes: dict[str, datetime] = {}
        self._warned: dict[str, str] = {}

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

    @property
    def status(self) -> str:
        """Return the overall status of the person, see ``STATUSES``."""
        if (
            self.last_reading_time is None
            or dt_util.utcnow() - self.last_reading_time > self.max_age
            or self._running(ALARM_DATA_LOSS)
        ):
            return STATUS_NO_DATA
        for alarm in STATUS_ALARMS:
            if self._running(alarm):
                return alarm
        return STATUS_PAUSED if self.paused else STATUS_OK

    @property
    def status_attributes(self) -> dict[str, Any]:
        """Return the latest reading and the running alarms."""
        reading = self.source.reading
        unit = self._unit()
        return {
            "glucose": self._display(reading.value, unit),
            "unit": unit,
            "trend_arrow": reading.trend_arrow,
            "rate": self._display_rate(unit),
            "reading_time": _iso(self.last_reading_time),
            "active_alarms": [
                alarm
                for alarm, engine in self.engines.items()
                if engine.state is AlarmState.ACTIVE
            ],
            "snoozed_alarms": [
                alarm
                for alarm, engine in self.engines.items()
                if engine.state is AlarmState.SNOOZED
            ],
        }

    def _running(self, alarm: str) -> bool:
        engine = self.engines.get(alarm)
        return engine is not None and engine.state in RUNNING_STATES

    def _display_rate(self, unit: str) -> float | None:
        """Return the own rate of change per minute in ``unit``, rounded."""
        converted = from_mg_dl(self.rate, unit)
        if converted is None:
            return None
        return round(converted, 1 if unit == MG_DL else 2)

    @staticmethod
    def _display(value: float | None, unit: str) -> float | None:
        """Return a mg/dL value in ``unit``, rounded for display."""
        converted = from_mg_dl(value, unit)
        if converted is None:
            return None
        return round(converted, 0 if unit == MG_DL else 1)

    @property
    def unit(self) -> str:
        """Return the unit of the glucose data."""
        return self._unit()

    display = _display

    def text(self, key: str, **placeholders: Any) -> str:
        """Return a translated text."""
        return self._text(key, **placeholders)

    def range_thresholds(self) -> tuple[float | None, float | None]:
        """Return the target range in mg/dL from the low and high thresholds.

        Uses the low (else urgent low) and high (else urgent high) thresholds,
        whether or not those alarms are active.
        """

        def first(alarms: tuple[str, ...]) -> float | None:
            for alarm in alarms:
                options = self._options[alarm]
                if options.get(CONF_THRESHOLD_ENTITY) or (
                    options.get(CONF_THRESHOLD) is not None
                ):
                    return self._threshold(options)
            return None

        return first(tuple(reversed(LOW_ALARMS))), first(HIGH_ALARMS)

    @callback
    def async_save(self) -> None:
        """Store the state soon."""
        self._store.async_delay_save(self._data_to_store, 1)

    @callback
    def async_notify_listeners(self) -> None:
        """Tell the entities about a change."""
        for update_callback in list(self._listeners):
            update_callback()

    @callback
    def async_fire(self, event_type: str, data: dict[str, Any]) -> None:
        """Pass an event to the event entities."""
        for listener in list(self._event_listeners):
            listener(event_type, data)

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
            for key in (
                CONF_THRESHOLD_ENTITY,
                CONF_RATE_ENTITY,
                CONF_BATTERY_ENTITY,
                CONF_CHARGING_ENTITY,
                CONF_TIME_ENTITY,
                CONF_BATTERY_LIMIT_ENTITY,
                CONF_LAST_CHANGE_ENTITY,
                CONF_WEAR_DURATION_ENTITY,
            )
            if (entity_id := self._options[alarm].get(key))
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
        if self.report is not None:
            self.report.async_start()
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
    def async_add_event_listener(self, listener: EventListener) -> CALLBACK_TYPE:
        """Call ``listener(event_type, data)`` for every event."""
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

    def records_changes(self, alarm: str) -> bool:
        """Return True if the integration records the changes of a reminder.

        Without a last change entity the change is recorded with the button
        or the action; with one, only the entity counts.
        """
        return alarm in CHANGE_ALARMS and not self._options[alarm].get(
            CONF_LAST_CHANGE_ENTITY
        )

    def last_change(self, alarm: str) -> datetime | None:
        """Return the time of the last change of a change reminder."""
        if entity_id := self._options[alarm].get(CONF_LAST_CHANGE_ENTITY):
            value = state_value(self.hass.states.get(entity_id))
            return None if value is None else self.datetime_from_state(value)
        return self.changes.get(alarm)

    @staticmethod
    def datetime_from_state(value: str) -> datetime | None:
        """Return the moment of a datetime or date state (date: local midnight)."""
        if (moment := dt_util.parse_datetime(value)) is None:
            return None
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=dt_util.get_default_time_zone())
        return dt_util.as_utc(moment)

    def wear_duration(self, alarm: str) -> timedelta | None:
        """Return the wear duration of a change reminder; an entity wins."""
        options = self._options[alarm]
        if entity_id := options.get(CONF_WEAR_DURATION_ENTITY):
            # Without a known time unit nothing is guessed.
            factor = DURATION_UNITS.get(sensor_unit(self.hass, entity_id) or "")
            value = parse_number(state_value(self.hass.states.get(entity_id)))
            if factor is None or value is None or value <= 0:
                return None
            return minutes(value * factor)
        return duration(options.get(CONF_WEAR_DURATION))

    def due(self, alarm: str) -> datetime | None:
        """Return when a change reminder starts.

        The last change plus the wear duration, or the fixed time on that day.
        """
        last = self.last_change(alarm)
        wear = self.wear_duration(alarm)
        if last is None or wear is None:
            return None
        due = last + wear
        options = self._options[alarm]
        if not options.get(CONF_DUE_TIME) and not options.get(CONF_TIME_ENTITY):
            return due
        if (time := self._time_option(options, CONF_DUE_TIME)) is None:
            return None
        return dt_util.as_utc(
            dt_util.as_local(due).replace(
                hour=time.hour, minute=time.minute, second=time.second, microsecond=0
            )
        )

    @callback
    def async_record_change(self, alarm: str, when: datetime | None = None) -> None:
        """Record a change (now or at ``when``); ends the reminder."""
        self.changes[alarm] = dt_util.as_utc(when or dt_util.utcnow())
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
        self._track_rate(reading, now)
        if self.pause_until is not None and now >= self.pause_until:
            self.pause_until = None
        self._async_update_issue(reading)

        for alarm, engine in self.engines.items():
            if alarm == ALARM_CHARGING:
                condition = self._charging_condition(now)
            elif alarm in CHANGE_ALARMS:
                condition = self._change_condition(alarm, now)
            elif self.reading_time_known:
                condition = self._condition(alarm, reading, now)
            else:
                continue
            phases = engine.update(now, condition, self._may_start(alarm))
            self._async_notify_all(alarm, phases, now)
        for alarm in self.engines:
            if alarm in CHANGE_ALARMS:
                self._async_check_warning(alarm, now)

        self._async_schedule(now)
        self.async_save()
        self.async_notify_listeners()

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
        if alarm in RATE_ALARMS:
            if reading.value is None or too_old:
                return Condition.UNKNOWN
            return self._rate_condition(alarm, reading, options)
        if (
            reading.value is None
            or too_old
            or (threshold := self._threshold(options)) is None
        ):
            return Condition.UNKNOWN
        offset = to_mg_dl(float(options.get(CONF_CLEAR_OFFSET) or 0), self._unit()) or 0
        if alarm in HIGH_ALARMS:
            if reading.value > threshold:
                return Condition.ALARM
            if reading.value <= threshold - offset:
                return Condition.CLEAR
            return Condition.BETWEEN
        if reading.value < threshold:
            return Condition.ALARM
        if reading.value >= threshold + offset:
            return Condition.CLEAR
        return Condition.BETWEEN

    def _charging_condition(self, now: datetime) -> Condition:
        """Return the condition of the charging reminder.

        From the reminder time until midnight: alarm while the phone is not
        charging and the battery is at or below the limit. Charging ends the
        alarm at any time; after midnight a running alarm waits for charging.
        """
        options = self._options[ALARM_CHARGING]
        charging = self._is_charging(options[CONF_CHARGING_ENTITY])
        if charging is None:
            return Condition.UNKNOWN
        if charging:
            return Condition.CLEAR
        start = self._reminder_start(now)
        if start is None or now < start:
            return Condition.UNKNOWN
        battery = parse_number(
            state_value(self.hass.states.get(options[CONF_BATTERY_ENTITY]))
        )
        if battery is None or (limit := self._battery_limit(options)) is None:
            return Condition.UNKNOWN
        return Condition.ALARM if battery <= limit else Condition.CLEAR

    def _change_condition(self, alarm: str, now: datetime) -> Condition:
        """Return the condition of a change reminder: alarm from the due time."""
        if (due := self.due(alarm)) is None:
            return Condition.UNKNOWN
        return Condition.ALARM if now >= due else Condition.CLEAR

    def _warning(self, alarm: str) -> timedelta | None:
        return duration(self._options[alarm].get(CONF_WARNING))

    @callback
    def _async_check_warning(self, alarm: str, now: datetime) -> None:
        """Fire the "due soon" event once per due time, within the warning.

        A warning that may not start (paused, away) is sent later, as long as
        the change is not due yet.
        """
        if (
            (lead := self._warning(alarm)) is None
            or (due := self.due(alarm)) is None
            or not due - lead <= now < due
            or self._warned.get(alarm) == due.isoformat()
            or not self._may_start(alarm)
        ):
            return
        self._warned[alarm] = due.isoformat()
        variables = self._variables(alarm, Phase.TRIGGERED, now)
        name = self.entry.title
        variables |= {
            "phase": TRIGGER_SOON,
            "title": self._text(f"{alarm}_{TRIGGER_SOON}", name=name),
            "message": self._text(
                "change_soon_message", duration=_format_duration(due - now)
            ),
        }
        self.async_fire(f"{alarm}_{TRIGGER_SOON}", variables)

    def _is_charging(self, entity_id: str) -> bool | None:
        """Return whether the phone charges, ``None`` if unknown."""
        if (value := state_value(self.hass.states.get(entity_id))) is None:
            return None
        return self.charging_from_state(value)

    @staticmethod
    def charging_from_state(value: str) -> bool | None:
        """Return whether a charging state means charging, ``None`` if unknown."""
        value = value.casefold()
        if value in (STATE_ON, *CHARGING_STATES):
            return True
        if value in (STATE_OFF, *NOT_CHARGING_STATES):
            return False
        return None

    @staticmethod
    def time_from_state(value: str) -> dt_time | None:
        """Return the time of day of a time or datetime state."""
        if (time := dt_util.parse_time(value)) is not None:
            return time
        if (moment := dt_util.parse_datetime(value)) is None:
            return None
        return dt_util.as_local(moment).time()

    def _battery_limit(self, options: Mapping[str, Any]) -> float | None:
        """Return the battery limit in percent; an entity takes precedence."""
        if entity_id := options.get(CONF_BATTERY_LIMIT_ENTITY):
            return parse_number(state_value(self.hass.states.get(entity_id)))
        return parse_number(options.get(CONF_BATTERY_LIMIT))

    def _reminder_start(self, now: datetime) -> datetime | None:
        """Return today's reminder time (local day of ``now``)."""
        time = self._time_option(self._options[ALARM_CHARGING], CONF_REMINDER_TIME)
        if time is None:
            return None
        return dt_util.as_local(now).replace(
            hour=time.hour, minute=time.minute, second=time.second, microsecond=0
        )

    def _time_option(self, options: Mapping[str, Any], key: str) -> dt_time | None:
        """Return a time of day from a field; the time entity takes precedence."""
        value: str | None = options.get(key)
        if entity_id := options.get(CONF_TIME_ENTITY):
            value = state_value(self.hass.states.get(entity_id))
        return None if value is None else self.time_from_state(value)

    def _rate_condition(
        self, alarm: str, reading: GlucoseReading, options: Mapping[str, Any]
    ) -> Condition:
        """Return the condition of a rapid change alarm."""
        if options.get(CONF_DETECTION) == DETECTION_TREND:
            if reading.trend is None or reading.trend in UNKNOWN_TRENDS:
                return Condition.UNKNOWN
            fast = FAST_TRENDS[alarm]
            if options.get(CONF_TREND_LEVEL) == TREND_LEVEL_VERY_QUICKLY:
                fast = fast[:1]
            return Condition.ALARM if reading.trend in fast else Condition.CLEAR
        if (rate := self.rate) is None or (limit := self._rate_limit(options)) is None:
            return Condition.UNKNOWN
        if alarm == ALARM_RAPID_FALL:
            return Condition.ALARM if rate <= -limit else Condition.CLEAR
        return Condition.ALARM if rate >= limit else Condition.CLEAR

    def _rate_limit(self, options: Mapping[str, Any]) -> float | None:
        """Return the rate limit of a rapid change alarm in mg/dL per minute."""
        if entity_id := options.get(CONF_RATE_ENTITY):
            # Without a known rate unit nothing is guessed.
            unit = RATE_UNITS.get(sensor_unit(self.hass, entity_id) or "")
            value = parse_number(state_value(self.hass.states.get(entity_id)))
            return None if value is None else to_mg_dl(abs(value), unit)
        if (limit := options.get(CONF_RATE_LIMIT)) is None:
            return None
        return to_mg_dl(abs(float(limit)), self._unit())

    @property
    def rate(self) -> float | None:
        """Return the own rate of change in mg/dL per minute."""
        if self._latest is None or self._previous is None:
            return None
        (time, value), (previous_time, previous_value) = self._latest, self._previous
        minutes = (time - previous_time).total_seconds() / 60
        if not 0 < minutes <= MAX_RATE_GAP_MINUTES:
            return None
        return (value - previous_value) / minutes

    def _track_rate(self, reading: GlucoseReading, now: datetime) -> None:
        """Remember the latest two readings for the own rate of change.

        Value and reading time may arrive in separate updates, in any order. A
        value that changes shortly after a new reading time belongs to it; a
        value that changes later belongs to the next reading and waits for its
        reading time.
        """
        if reading.reading_time is None or reading.value is None:
            return
        if self._latest is None or reading.reading_time > self._latest[0]:
            self._previous = self._latest
            self._latest = (reading.reading_time, reading.value)
            self._latest_at = now
        elif (
            reading.reading_time == self._latest[0]
            and now - self._latest_at <= RATE_VALUE_WINDOW
        ):
            self._latest = (reading.reading_time, reading.value)

    def _may_start(self, alarm: str) -> bool:
        """Return True if a new alarm may start now."""
        if alarm in PAUSABLE_ALARMS and self.paused:
            return False
        return not self._options[alarm].get(CONF_ONLY_WHEN_HOME) or self.at_home

    @property
    def at_home(self) -> bool:
        """Return True unless the person is known to be away.

        Without a person, or with an unknown presence, nothing is suppressed.
        """
        if not (person := self.entry.options.get(CONF_PERSON_ENTITY)):
            return True
        state = self.hass.states.get(person)
        return state is None or state.state in (
            STATE_HOME,
            STATE_UNKNOWN,
            STATE_UNAVAILABLE,
        )

    def _threshold(self, options: Mapping[str, Any]) -> float | None:
        """Return the threshold of an alarm in mg/dL: entity, else number."""
        if entity_id := options.get(CONF_THRESHOLD_ENTITY):
            return value_mg_dl(self.hass, entity_id, self.source.entities.unit)
        if (value := options.get(CONF_THRESHOLD)) is None:
            return None
        return to_mg_dl(float(value), self._unit())

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
        if (
            ALARM_CHARGING in self.engines
            and (start := self._reminder_start(now)) is not None
        ):
            times.extend((start, start + timedelta(days=1)))
        for alarm in self.engines:
            if alarm in CHANGE_ALARMS and (due := self.due(alarm)) is not None:
                times.append(due)
                if (lead := self._warning(alarm)) is not None:
                    times.append(due - lead)
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
        """Fire the alert or ended event of an alarm."""
        variables = self._variables(alarm, phase, now)
        _LOGGER.debug("%s: %s alarm %s", self.entry.title, alarm, phase)
        kind = TRIGGER_ALERT if phase in ALERT_PHASES else TRIGGER_ENDED
        if phase is Phase.TRIGGERED and self.report is not None:
            self.report.count(alarm)
        self.async_fire(f"{alarm}_{kind}", variables)

    def _variables(self, alarm: str, phase: Phase, now: datetime) -> dict[str, Any]:
        """Return the data of an alarm event."""
        reading = self.source.reading
        unit = self._unit()
        digits = 0 if unit == MG_DL else 1
        glucose = self._display(reading.value, unit)
        change = self._display(reading.change, unit)
        age = (
            None
            if self.last_reading_time is None
            else int((now - self.last_reading_time).total_seconds() // 60)
        )
        name = self.entry.title
        battery = None
        if alarm == ALARM_CHARGING:
            battery = parse_number(
                state_value(
                    self.hass.states.get(self._options[alarm][CONF_BATTERY_ENTITY])
                )
            )
        if phase is Phase.ACKNOWLEDGED or phase is Phase.RESOLVED:
            message = self._text(phase.value)
        elif alarm == ALARM_DATA_LOSS:
            message = self._text("data_loss_message", minutes=age)
        elif alarm == ALARM_CHARGING:
            message = self._text("charging_message", battery=_format(battery, 0))
        elif alarm in CHANGE_ALARMS:
            last = self.last_change(alarm)
            message = self._text(
                "change_message",
                duration=_format_duration(None if last is None else now - last),
            )
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
            "rate": self._display_rate(unit),
            "data_age_min": age,
            "battery": battery,
            "last_change": _iso(self.last_change(alarm))
            if alarm in CHANGE_ALARMS
            else None,
            "due": _iso(self.due(alarm)) if alarm in CHANGE_ALARMS else None,
            "title": self._text(alarm, name=name),
            "message": message,
            "tag": notification_tag(self.entry.entry_id, alarm),
            "icon": ALARM_ICONS[alarm],
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
        if self.report is not None:
            self.report.restore(data.get("report") or {})
        self.changes = {
            alarm: moment
            for alarm, value in (data.get("changes") or {}).items()
            if (moment := _parse_time(value)) is not None
        }
        self._warned = dict(data.get("warned") or {})

    def _data_to_store(self) -> dict[str, Any]:
        return {
            "alarms": {
                alarm: engine.status.as_dict() for alarm, engine in self.engines.items()
            },
            "last_reading_time": _iso(self.last_reading_time),
            "pause_until": _iso(self.pause_until),
            "report": None if self.report is None else self.report.as_dict(),
            # Kept for all reminders: switching one off keeps its last change.
            "changes": {alarm: _iso(moment) for alarm, moment in self.changes.items()},
            "warned": self._warned,
        }


def _format(value: float | None, digits: int) -> str:
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def _format_duration(value: timedelta | None) -> str:
    """Return a duration as whole hours, or minutes below one hour."""
    if value is None:
        return "–"
    total = max(int(value.total_seconds() // 60), 0)
    return f"{total // 60} h" if total >= 60 else f"{total} min"


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    return dt_util.parse_datetime(value)
