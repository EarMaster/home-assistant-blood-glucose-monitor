# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-11-07

### Added
- Setup per person with a mandatory notice that this is not a medical device and does not replace the alarms of a CGM, pump or medical app
- Glucose sensor, optional person, and optional trend, change and reading time sensors, suggested from the same device as the glucose sensor
- Fallback to the `direction`, `delta` and `date` attributes of the glucose sensor (Nightscout)
- Works with any glucose source: every sensor can be selected and its current value is checked; the trend is understood as state key, Nightscout direction, common word or arrow
- Unit setting for sensors that do not report a unit; units and reading times are never guessed
- Urgent low, low and data loss alarms with threshold entities, delay, repeat, clear offset, acknowledge, snooze with re-check and an option to alarm only while the person is at home
- Device triggers per alarm ("started or repeated", "acknowledged or over") for notifications as automations, with ready-made, translated texts and the alarm data
- Acknowledge per alarm via button, `blood_glucose_monitor.acknowledge` action or mobile app notification action
- Pause switch for the low and data loss alarms that turns off by itself; urgent low is never paused
- Alarm state sensors and an alarm event entity; alarm states survive restarts
- Repair issue when the glucose data has no reading time
- Notice when another entry already monitors the selected glucose sensor
- Options to change the sensors later
- Diagnostics download showing how the glucose data is read and the alarm states
- English and German translations
