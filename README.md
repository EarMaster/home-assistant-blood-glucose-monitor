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
- Alarms for urgent low, low and data loss with acknowledge, snooze,
  re-check and pause; notifications as your own Home Assistant actions
- Diagnostics download showing how the glucose data and alarms are read

Planned next: high alarms, rapid change, night report and phone charging
reminder.

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

Under **Configure** each entry has a menu: glucose data, the urgent low, low
and data loss alarms, and the pause. Every alarm is off until you enable it.

| Alarm | Starts | Ends |
| --- | --- | --- |
| Urgent low | glucose below its threshold for the delay | glucose at threshold plus clear offset |
| Low | glucose below its threshold for the delay | glucose at threshold plus clear offset |
| Data loss | no new reading within the maximum data age | a new reading |

- **Thresholds** are entities: for example the threshold sensors of the
  glucose integration (suggested automatically when available) or an
  `input_number`. Each alarm has its own threshold.
- **Repeat:** an active alarm runs its action again in this interval
  (0 = once).
- **Acknowledge** silences an alarm for its snooze time. Afterwards the alarm
  is checked again and starts at once if it still applies. Ways to
  acknowledge: the *Acknowledge … alarm* button, the
  `blood_glucose_monitor.acknowledge` action, or a mobile app notification
  action with the id from `ack_action`. Each alarm of each entry is
  acknowledged on its own.
- **Pause:** the *Pause alarms* switch silences the low and data loss alarms
  for the configured duration and turns off by itself. Urgent low is never
  paused.
- **Only when the person is at home:** new alarms only start while the
  selected person is at home; a running alarm continues.
- **Stale data:** readings older than the maximum data age neither start nor
  end the glucose alarms; the data loss alarm covers this.
- **Restart:** alarm states survive a restart of Home Assistant.
- Without a reading time no alarms are possible; a repair issue tells you so.

Each alarm has an *action* (alarm starts and every repeat) and an *end
action* (acknowledged or over). Both get these variables:

| Variable | Content |
| --- | --- |
| `title`, `message` | ready-made texts in the language of Home Assistant |
| `alarm` | `urgent_low`, `low` or `data_loss` |
| `phase` | `triggered`, `repeat`, `acknowledged` or `resolved` |
| `glucose`, `unit`, `delta` | latest value and change in the unit of the glucose sensor |
| `trend`, `trend_arrow` | trend key and arrow |
| `data_age_min` | age of the latest reading in minutes |
| `person_name`, `entry_id` | the entry |
| `tag` | notification tag, unique per entry and alarm |
| `ack_action` | mobile app action id that acknowledges this alarm |

Example for the Home Assistant Companion app, action:

```yaml
action: notify.mobile_app_your_phone
data:
  title: "{{ title }}"
  message: "{{ message }}"
  data:
    tag: "{{ tag }}"
    actions:
      - action: "{{ ack_action }}"
        title: Acknowledge
```

End action:

```yaml
action: notify.mobile_app_your_phone
data:
  message: clear_notification
  data:
    tag: "{{ tag }}"
```

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
