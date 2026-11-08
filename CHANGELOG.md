# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- One event entity per alarm and one for the report: automations use the trigger "Event received" with the event types `<alarm>_alert`, `<alarm>_ended`, `<change>_soon` and `report`; the event data are attributes of the entity (`trigger.to_state.attributes`)
- Documentation site with an automation builder; the device page (Visit) and the Configure menu link to it with the entities of the person

### Removed
- **Breaking:** the device triggers and the shared "Alarm" event entity; move automations to the new event entities (`trigger.event.data.x` becomes `trigger.to_state.attributes.x`)

## [0.5.1] - 2026-11-08

### Added
- Reports: option "only when the person is at home" for the "Report" trigger; the report and the "Last report" sensor are updated anyway

## [0.5.0] - 2026-11-08

### Added
- Change reminders for cannula, CGM sensor and insulin reservoir: due at the last change plus the wear duration (field or entity) or at a fixed time on the due day; the last change comes from an entity or is recorded with a "changed" button or the new action `blood_glucose_monitor.record_change`; due sensor, optional "due soon" warning trigger, and acknowledge, snooze, repeat, pause and "only when home" like the other alarms

### Fixed
- The state sensor of the charging reminder is no longer unavailable when the glucose data has no reading time

## [0.4.0] - 2026-11-08

### Added
- Charging reminder: from the reminder time until midnight while the phone is not charging and the battery is at or below the limit, with acknowledge, snooze, repeat and pause; battery and charging sensors are suggested from the person's phone; time and limit as field or entity
- Reports per period of a schedule, input boolean or binary sensor: device trigger "Report" with start, end, minimum, maximum, mean, time below/in/above range, data coverage and the alarms of the period, plus a "Last report" sensor

## [0.3.0] - 2026-11-07

### Added
- High and urgent high alarms with threshold entities (the Nightscout target range top and urgent high threshold are suggested)
- Rapid fall and rapid rise alarms, detected by the trend of the glucose data or by the own rate of change with a limit as number or entity
- Rate of change in the status sensor and in the trigger data
- Status sensor states for the new alarms

### Changed
- The pause applies to all alarms except urgent low

## [0.2.1] - 2026-11-07

### Added
- Status sensor per person with the most important current state (no data, urgent low, low, paused, OK), the latest glucose value and the running alarms

### Changed
- No enable switch per alarm: urgent low and low are active once they have a threshold (empty threshold = off), the data loss alarm is always active; notifications only come from your automations on the device triggers

## [0.2.0] - 2026-11-07

### Changed
- Notifications are automations: every enabled alarm adds the device triggers "started or repeated" and "acknowledged or over" to the person's device; the alarm data (title, message, tag, ack_action, glucose, ...) is available as `trigger.event.data`

### Removed
- Action and end action fields of the alarms. Actions set up in 0.1.0 no longer run; recreate them as automations with the device triggers

## [0.1.0] - 2026-11-07

### Added
- Setup per person with a mandatory notice that this is not a medical device and does not replace the alarms of a CGM, pump or medical app
- Glucose sensor, optional person, and optional trend, change and reading time sensors, suggested from the same device as the glucose sensor
- Fallback to the `direction`, `delta` and `date` attributes of the glucose sensor (Nightscout)
- Works with any glucose source: every sensor can be selected and its current value is checked; the trend is understood as state key, Nightscout direction, common word or arrow
- Unit setting for sensors that do not report a unit; units and reading times are never guessed
- Urgent low, low and data loss alarms with threshold entities, delay, repeat, clear offset, acknowledge, snooze with re-check and an option to alarm only while the person is at home
- Alarm notifications as your own actions (start/repeat and end) with ready-made, translated texts and variables
- Acknowledge per alarm via button, `blood_glucose_monitor.acknowledge` action or mobile app notification action
- Pause switch for the low and data loss alarms that turns off by itself; urgent low is never paused
- Alarm state sensors and an alarm event entity; alarm states survive restarts
- Repair issue when the glucose data has no reading time
- Notice when another entry already monitors the selected glucose sensor
- Options to change the sensors later
- Diagnostics download showing how the glucose data is read and the alarm states
- English and German translations
