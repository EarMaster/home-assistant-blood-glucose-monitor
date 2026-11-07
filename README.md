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

Work in progress. The current version (0.1) contains the foundation only:

- Setup with a mandatory acknowledgement of the notice above
- One entry per person: glucose sensor and optional person
- Optional trend, change and reading time sensors, suggested automatically
  from the same device as the glucose sensor
- Fallback to the `direction`, `delta` and `date` attributes of the glucose
  sensor (as provided by Nightscout)
- Diagnostics download showing how the glucose data is read

Planned next: low/urgent low alarms with acknowledge, snooze and re-check,
missing data detection, high alarms, rapid change, night report and phone
charging reminder. Notifications will be configured as free Home Assistant
actions per feature.

## Requirements

- Home Assistant 2026.11 or newer
- An integration that provides a glucose sensor (device class
  `blood_glucose_concentration`, unit mg/dL or mmol/L)

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
   empty to use the attributes of the glucose sensor instead.

All settings except the name can be changed later via **Configure**.

| Data | Preferred source | Fallback |
| --- | --- | --- |
| Glucose value | glucose sensor | – |
| Trend | enum sensor (`steady`, `falling_quickly`, …) | `direction` attribute |
| Change | glucose concentration sensor | `delta` attribute (mg/dL) |
| Reading time | timestamp sensor | `date` attribute, then last value change |

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

All glucose values in tests are synthetic. Please do not add real health data
to issues, tests or fixtures.

## License

[MIT](LICENSE)
