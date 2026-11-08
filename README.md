<p align="center">
  <img src="custom_components/blood_glucose_monitor/brand/icon.png" width="96" alt="">
</p>

# Blood Glucose Monitor for Home Assistant

> [!CAUTION]
> **This is not a medical device and not a replacement for real alarms.**
> Blood Glucose Monitor only adds *extra* hints and information to Home
> Assistant. It does **not** replace the alarms of your CGM, insulin pump or
> medical app (for example Dexcom, LibreLink, CamAPS FX or xDrip+). Keep those
> alarms switched on at all times.
>
> Notifications from Home Assistant can be delayed or not arrive at all, for
> example when Home Assistant, your network or the glucose data source is down.
> Never rely on them alone. Use at your own risk; there is no warranty of any
> kind (see [LICENSE](LICENSE)).
>
> **Deutsch:** Diese Integration ist **kein Medizinprodukt** und **ersetzt
> keine Alarme** von CGM, Insulinpumpe oder Medizin-Apps. Lass diese Alarme
> immer eingeschaltet. Benachrichtigungen aus Home Assistant können verspätet
> oder gar nicht ankommen.

A custom integration that turns the glucose data of another integration (for
example [Nightscout](https://www.home-assistant.io/integrations/nightscout) or
[Dexcom](https://www.home-assistant.io/integrations/dexcom)) into optional,
configurable hints for everyday life: one entry per person, every feature can
be switched off, and you decide with any Home Assistant action how you want to
be notified.

## Status

Work in progress. The current version (0.1) contains:

- Setup with a mandatory acknowledgement of the notice above
- One entry per person: glucose sensor and optional person
- Optional trend, change and reading time sensors, suggested automatically
  from the same device as the glucose sensor
- Fallback to the `direction`, `delta` and `date` attributes of the glucose
  sensor (as provided by Nightscout)
- Any glucose source: every sensor can be selected, its current value is
  checked during setup
- Alarms for urgent low, low, high, urgent high, rapid fall, rapid rise and
  data loss with acknowledge, snooze, re-check and pause; notifications as
  automations with device triggers
- Status sensor per person
- Charging reminder for the phone, as alarm with the same acknowledge,
  snooze and pause
- Change reminders for cannula, CGM sensor and insulin reservoir, with due
  sensor, "changed" button and optional warning
- Reports per period of a schedule (for example night, school): statistics
  of the period as trigger and sensor
- Diagnostics download showing how the glucose data and alarms are read

## Requirements

- Home Assistant 2026.11 or newer
- An integration that provides a sensor with the current glucose value in
  mg/dL or mmol/L, for example Nightscout, Dexcom or a custom integration. If
  the sensor does not report a unit, you set it during setup.

## Installation

### Marketplace

Add this repository as a custom repository of type *Integration* in the
Marketplace:

[![Open your Home Assistant instance and open this repository in the Marketplace.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=EarMaster&repository=home-assistant-blood-glucose-monitor&category=integration)

Download *Blood Glucose Monitor*, restart Home Assistant and add the
integration under **Settings → Devices & services**.

### Manual

Copy `custom_components/blood_glucose_monitor` into the `custom_components`
folder of your Home Assistant configuration and restart Home Assistant.

## Configuration

Add one entry per person:

1. Read and confirm the notice.
2. Enter the name and select the glucose sensor (and optionally the person).
3. Check the suggested trend, change and reading time sensors. Leave a field
   empty to use the attributes of the glucose sensor instead. Select the unit
   if the glucose or change sensor does not report one.

All settings except the name can be changed later via **Configure**.

| Data | Preferred source | Fallback |
| --- | --- | --- |
| Glucose value | glucose sensor | – |
| Trend | trend sensor | `direction` attribute |
| Change | change sensor | `delta` attribute (unit of the glucose sensor) |
| Reading time | reading time sensor | `date` attribute |

Nothing is guessed:

- Sensors without a unit are only read once you have set the unit.
- Without a reading time, the age of the data is unknown and no alarms are
  possible. The time of the last value change is not used, because the same
  value twice in a row would look like missing data.

The trend is understood as state key (`steady`, `falling_quickly`, …),
Nightscout direction (`Flat`, `SingleDown`, …), common word (`stable`,
`rising fast`, `decreasing`, …) or arrow (`→`, `↘`, `⇊`, …). Setup tells you
when the current value of a selected sensor cannot be read.

## Alarms

Under **Configure** each entry has a menu: glucose data, one item per alarm
and the pause. The threshold alarms are active once they have a threshold
(leave it empty to switch them off), the rapid change alarms once a detection
is selected; the data loss alarm is always active. Without an automation on
their triggers, alarms only change their state sensors.

| Alarm | Starts | Ends |
| --- | --- | --- |
| Urgent low | glucose below its threshold for the delay | glucose at threshold plus clear offset |
| Low | glucose below its threshold for the delay | glucose at threshold plus clear offset |
| High | glucose above its threshold for the delay | glucose at threshold minus clear offset |
| Urgent high | glucose above its threshold for the delay | glucose at threshold minus clear offset |
| Rapid fall | fast fall for the delay (see below) | no longer a fast fall |
| Rapid rise | fast rise for the delay (see below) | no longer a fast rise |
| Data loss | no new reading within the maximum data age | a new reading |

- **Thresholds** are entities: for example the threshold sensors of the
  glucose integration (suggested automatically when available) or an
  `input_number`. Each alarm has its own threshold.
- **Rapid change** is detected either by the **trend** of the glucose data
  (from "quickly" or only "very quickly") or by the **own rate of change**
  between the last two readings (at most 15 minutes apart) with a limit per
  minute. The limit is a number in the unit of the glucose data per minute,
  or an entity with the unit `mg/dL/min` or `mmol/L/min`, which takes
  precedence.
- **Repeat:** an active alarm fires its trigger again in this interval
  (0 = once).
- **Acknowledge** silences an alarm for its snooze time. Afterwards the alarm
  is checked again and starts at once if it still applies. Ways to
  acknowledge: the *Acknowledge … alarm* button, the
  `blood_glucose_monitor.acknowledge` action, or a mobile app notification
  action with the id from `ack_action`. Each alarm of each entry is
  acknowledged on its own.
- **Pause:** the *Pause alarms* switch silences all alarms except urgent low
  for the configured duration and turns off by itself. Urgent low is never
  paused.
- **Only when the person is at home:** new alarms only start while the
  selected person is at home; a running alarm continues.
- **Stale data:** readings older than the maximum data age neither start nor
  end the glucose alarms; the data loss alarm covers this.
- **Restart:** alarm states survive a restart of Home Assistant.
- Without a reading time no glucose alarms are possible; a repair issue tells
  you so. The charging and change reminders do not need glucose data.

### Notifications

Notifications are automations: the integration only decides *when* to alarm,
you decide *how*. Every active alarm adds two triggers to the device of the
person (in the automation editor under **Device**):

| Trigger | Fires when |
| --- | --- |
| *… alarm started or repeated* | the alarm starts and on every repeat |
| *… alarm acknowledged or over* | the alarm is acknowledged or ends |

The automation gets the alarm data as `trigger.event.data`:

| Field | Content |
| --- | --- |
| `title`, `message` | ready-made texts in the language of Home Assistant |
| `alarm` | `urgent_low`, `low`, `high`, `urgent_high`, `rapid_fall`, `rapid_rise`, `data_loss`, `charging`, `cannula_change`, `sensor_change` or `reservoir_change` |
| `phase` | `triggered`, `repeat`, `acknowledged` or `resolved` (`soon` for the warning of a change reminder) |
| `glucose`, `unit`, `delta` | latest value and change in the unit of the glucose sensor |
| `rate` | own rate of change per minute in that unit |
| `trend`, `trend_arrow` | trend key and arrow |
| `data_age_min` | age of the latest reading in minutes |
| `person_name`, `entry_id` | the entry |
| `tag` | notification tag, unique per entry and alarm |
| `ack_action` | mobile app action id that acknowledges this alarm |
| `battery` | battery level of the phone (charging reminder only) |
| `last_change`, `due` | last change and due time (change reminders only) |

Example for the Home Assistant Companion app (select the device and the
trigger in the editor, then switch the action to YAML):

```yaml
triggers:
  - trigger: device
    domain: blood_glucose_monitor
    device_id: <device of the person>
    type: low_alert
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: "{{ trigger.event.data.title }}"
      message: "{{ trigger.event.data.message }}"
      data:
        tag: "{{ trigger.event.data.tag }}"
        actions:
          - action: "{{ trigger.event.data.ack_action }}"
            title: Acknowledge
```

And to remove the notification again (trigger type `low_ended`):

```yaml
actions:
  - action: notify.mobile_app_your_phone
    data:
      message: clear_notification
      data:
        tag: "{{ trigger.event.data.tag }}"
```

### Charging reminder

The charging reminder is an alarm like the others (acknowledge, snooze,
repeat, pause, triggers): from the reminder time until midnight it starts
while the phone is not charging and the battery is at or below the limit, and
it ends as soon as the phone charges. After midnight a running reminder waits
for charging; no new one starts before the next reminder time.

- **Battery level** and **charging state** are suggested from the phone of the
  person (via the device trackers of the person). The charging state can be a
  binary sensor (on = charging) or a sensor like the battery state of the
  mobile app (`charging`, `full`, `discharging`, `not_charging`).
- **Reminder time** and **battery limit** are fields; an entity (for example
  an `input_datetime` or `input_number`) takes precedence.
- Leave the battery and charging sensors empty to switch the reminder off.

### Change reminders

Cannula, CGM sensor and insulin reservoir each have their own reminder. A
reminder is on once it has a **wear duration** (a field with days and hours,
or an entity with the unit `d`, `h` or `min`, which takes precedence) and
starts when the change is due:

- **Due:** the last change plus the wear duration, or, with a **fixed time**,
  at that time on the due day (a field or a time entity, which takes
  precedence). The *… change due* sensor shows the due time.
- **Last change:** select an entity with the time of the last change, for
  example from the glucose integration, and only that entity counts.
  Without one, record a change with the *… changed* button or the
  `blood_glucose_monitor.record_change` action (optionally with a time in the
  past). The button can be pressed by an automation, for example from a
  physical button.
- The reminder ends with the next change. Acknowledge, snooze, repeat, pause
  and "only when home" work as for the alarms.
- **Warning:** optionally the *… change due soon* trigger fires once this long
  before the reminder; while the person is away or alarms are paused it is
  sent as soon as possible before the due time.

### Reports

Select an entity that is on during the periods you want a report for,
typically a **schedule** helper with several blocks (for example night
22:00–07:00 and school 08:00–13:00); an `input_boolean` or a binary sensor
works too. When a period ends, the *Report* trigger of the person's device
fires and the *Last report* sensor (share of time in range) is updated:

| Field | Content |
| --- | --- |
| `start`, `end`, `duration_min` | the period |
| `glucose_min`, `glucose_max`, `glucose_mean`, `unit` | values in the unit of the glucose sensor; the mean is weighted by time |
| `below`, `in_range`, `above` | share of the time in percent, range from the low (else urgent low) and high (else urgent high) thresholds |
| `coverage` | share of the period with glucose data in percent |
| `alarms`, `low_alarms` | number of alarms that started in the period |
| `title`, `message` | ready-made texts |

The statistics come from the history of the glucose sensor (recorder). A
period that ends while Home Assistant is restarting is reported afterwards.

Every entry has a *Status* sensor with the most important current state:
`no_data` (data loss or no reading time), `urgent_low`, `low`,
`rapid_fall`, `urgent_high`, `high`, `rapid_rise`, `paused` or `ok`. Its
attributes hold the latest glucose value with unit, trend arrow and rate of
change, the reading time and the active and snoozed alarms.

Per entry there are also a state sensor per alarm (`idle`, `pending`,
`active`, `snoozed`) and an *Alarm* event entity that records every alarm
event in the logbook and can trigger automations.

## Development

The code, entity names and UI texts are in English, translations live in
`custom_components/blood_glucose_monitor/translations/`.

Tests use [pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component)
and need Linux (Home Assistant does not run on Windows):

```bash
pip install -r requirements_test.txt
ruff check . && ruff format --check .
pytest --cov
```

`scripts/test.sh` runs the same in a Docker container. GitHub Actions run the
tests, [hassfest](https://github.com/home-assistant/actions) and the
Marketplace (HACS) validation on every push.

### Branches and releases

- `develop` holds the work in progress; pull requests for changes go there.
  New entries go into the `[Unreleased]` section of [CHANGELOG.md](CHANGELOG.md).
- `main` is the released state. A release is a pull request from `develop`
  into `main` with a higher version in `manifest.json` and its own
  CHANGELOG section. Merging it (as a merge commit) creates the tag and the
  GitHub release automatically.
- `scripts/check_version.py` makes sure the version only grows; it runs on
  every push and, stricter, on pull requests into `main`.

All glucose values in tests are synthetic. Please do not add real health data
to issues, tests or fixtures.

## License

[MIT](LICENSE)
