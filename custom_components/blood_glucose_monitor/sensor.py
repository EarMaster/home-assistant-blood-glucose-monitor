"""Sensors of the Blood Glucose Monitor integration: status, alarm states,
due times, last report, GMI and estimated HbA1c."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BloodGlucoseMonitorConfigEntry
from .alarm import AlarmState
from .const import ALARMS_WITHOUT_GLUCOSE, CHANGE_ALARMS
from .entity import BloodGlucoseMonitorEntity
from .estimates import ESTIMATED_A1C, GMI
from .monitor import STATUSES

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BloodGlucoseMonitorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the status sensor, one state sensor per active alarm and one due
    sensor per active change reminder.
    """
    monitor = entry.runtime_data.monitor
    async_add_entities(
        [
            StatusSensor(entry),
            *([LastReportSensor(entry)] if monitor.report else []),
            *(
                EstimateSensor(entry, kind)
                for kind in (GMI, ESTIMATED_A1C)
                if monitor.estimate
            ),
            *(AlarmStateSensor(entry, alarm) for alarm in monitor.alarms),
            *(
                DueSensor(entry, alarm)
                for alarm in monitor.alarms
                if alarm in CHANGE_ALARMS
            ),
        ]
    )


class StatusSensor(BloodGlucoseMonitorEntity, SensorEntity):
    """Overall status of the person: the most important running alarm."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_translation_key = "status"

    def __init__(self, entry: BloodGlucoseMonitorConfigEntry) -> None:
        """Initialize."""
        super().__init__(entry, "status")
        self._attr_options = list(STATUSES)

    @property
    def native_value(self) -> str:
        """Return the status."""
        return self.monitor.status

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the latest reading and the running alarms."""
        return self.monitor.status_attributes


class LastReportSensor(BloodGlucoseMonitorEntity, SensorEntity):
    """The last report: share of time in range, statistics as attributes."""

    _attr_translation_key = "last_report"
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, entry: BloodGlucoseMonitorConfigEntry) -> None:
        """Initialize."""
        super().__init__(entry, "last_report")

    @property
    def native_value(self) -> float | None:
        """Return the share of time in the target range."""
        report = self.monitor.report
        return (
            None if report is None or report.last is None else report.last["in_range"]
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the statistics of the last report."""
        report = self.monitor.report
        if report is None or report.last is None:
            return {}
        return {
            key: value
            for key, value in report.last.items()
            if key not in ("entry_id", "person_name", "title")
        }


class AlarmStateSensor(BloodGlucoseMonitorEntity, SensorEntity):
    """State of one alarm: idle, pending, active or snoozed."""

    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(self, entry: BloodGlucoseMonitorConfigEntry, alarm: str) -> None:
        """Initialize."""
        super().__init__(entry, f"{alarm}_alarm")
        self._attr_options = [state.value for state in AlarmState]
        self.alarm = alarm
        self._attr_translation_key = f"{alarm}_alarm"

    @property
    def available(self) -> bool:
        """Without a reading time no glucose alarms are possible."""
        return self.alarm in ALARMS_WITHOUT_GLUCOSE or self.monitor.reading_time_known

    @property
    def native_value(self) -> str:
        """Return the alarm state."""
        return self.monitor.state(self.alarm).value


class DueSensor(BloodGlucoseMonitorEntity, SensorEntity):
    """When a change (cannula, sensor or reservoir) is due."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, entry: BloodGlucoseMonitorConfigEntry, alarm: str) -> None:
        """Initialize."""
        super().__init__(entry, f"{alarm}_due")
        self.alarm = alarm
        self._attr_translation_key = f"{alarm}_due"

    @property
    def native_value(self) -> datetime | None:
        """Return the due time."""
        return self.monitor.due(self.alarm)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the last change and the wear duration."""
        last = self.monitor.last_change(self.alarm)
        wear = self.monitor.wear_duration(self.alarm)
        return {
            "last_change": None if last is None else last.isoformat(),
            "wear_duration_h": None if wear is None else wear.total_seconds() / 3600,
        }


class EstimateSensor(BloodGlucoseMonitorEntity, SensorEntity):
    """GMI or estimated HbA1c from the mean glucose of the period."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, entry: BloodGlucoseMonitorConfigEntry, kind: str) -> None:
        """Initialize."""
        super().__init__(entry, kind)
        self.kind = kind
        self._attr_translation_key = kind

    @property
    def native_value(self) -> float | None:
        """Return the value in percent; unknown without enough data."""
        assert self.monitor.estimate is not None
        return self.monitor.estimate.value(self.kind)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return mmol/mol, mean glucose, coverage and period."""
        assert self.monitor.estimate is not None
        return self.monitor.estimate.attributes(self.kind)
