# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.3.0] - 2026-11-08

### Added
- Sensors *GMI* (glucose management indicator) and *Estimated HbA1c* (ADAG) per person, in percent with the value in mmol/mol, the mean glucose and the coverage as attributes; calculated from the long-term statistics of the glucose sensor over a period (default 90 days, number or entity), unknown below 70 % coverage, updated hourly; a repair issue tells when the glucose sensor has no long-term statistics; on for new and existing entries, switched off with an empty period under **Configure → GMI and estimated HbA1c**

### Changed
- Automation builder: one notify action instead of a comma separated list (which repeated the notification per phone); for several phones the documentation explains a notify group, the default `notify.notify` sends to all phones with the Companion app
- Automation builder: without a channel name the notification channel is the name of the person from the event (`{{ event.person_name }}`), so it follows a renamed entry

## [1.2.0] - 2026-11-08

### Added
- Threshold alarms: the threshold can again be entered as a number (in the unit of the glucose data); a threshold entity takes precedence

### Changed
- Urgent low supersedes low (urgent high supersedes high): while the urgent alarm runs (pending, active or snoozed), the plain one neither starts nor repeats, and acknowledging the urgent alarm also acknowledges the plain one until the urgent alarm's snooze time ends (not the plain alarm's own); acknowledging low or high does not hold the urgent alarm

## [1.1.2] - 2026-11-08

### Added
- Alarm, reminder and report events have an `icon` attribute (the Material Design icon of the alarm); the automation builder uses it as notification icon

### Changed
- Icons: every alarm has a fixed icon on its state sensor and its event entity, so it stays recognizable in every state; urgent low/high use square icons, low/high round ones
- Automation builder: one trigger per selected event, with the event type as trigger ID and the name Home Assistant shows as alias; each trigger can be moved to its own automation
- Automation builder: without a notify action it uses `notify.notify`
- Automation builder: optional Android notification channel, by default the name of the person
- Automation builder: alarm notifications (started or repeated) have high importance

## [1.1.1] - 2026-11-08

### Changed
- Automation builder: the event data are a variable `event` (`{{ event.title }}` instead of `{{ trigger.to_state.attributes.title }}`), shorter and easier to adapt
- Automation builder: one trigger per kind of event with a trigger ID (`alert`, `ended`, `notify`); the actions choose by trigger, which the visual editor shows clearly
- A pull request that only changes the documentation site, README, scripts or tests can be merged without a new version; it publishes the site without a release

### Fixed
- Documentation site: the introduction of the builder and documentation pages no longer ends with a stray "#readme"

## [1.1.0] - 2026-11-08

### Added
- French, Spanish and Dutch translations
- The documentation site in English, German, French, Spanish and Dutch: the start page follows the browser language, a switcher changes it, and the builder link from Home Assistant opens the page in its language
- "Open in Marketplace" button and a "Get involved" section on the documentation site
- "About this project" section on the documentation site and in the README with support links (Liberapay, Buy Me a Coffee), also as the sponsor button on GitHub

## [1.0.1] - 2026-11-08

### Changed
- Names follow the terms of CGM apps and Nightscout: "Falling fast" and "Rising fast" instead of "Rapid fall/rise" alarm; German "dringend niedrig/hoch" instead of "sehr niedrig/hoch" and "Kanülenwechsel-Erinnerung" etc. Existing entity IDs stay the same
- The settings of the cannula and reservoir change reminders also name other common terms (for example infusion set, site change, pod; cartridge)

## [1.0.0] - 2026-11-08

### Added
- One event entity per alarm and one for the report: automations use the trigger "Event received" with the event types `<alarm>_alert`, `<alarm>_ended`, `<change>_soon` and `report`; the event data are attributes of the entity (`trigger.to_state.attributes`)
- Report: `tag` attribute, unique per entry, so a new report notification replaces the last one
- Documentation site with an automation builder; the device page (Visit) and the Configure menu link to it with the entities of the person, and the documentation link of the integration opens it

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
