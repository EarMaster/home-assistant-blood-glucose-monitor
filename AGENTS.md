# AGENTS.md

Guidance for coding agents working on this repository.

## What this is

A custom Home Assistant integration (`blood_glucose_monitor`, distributed via
the Marketplace, formerly called HACS; always say "Marketplace" in docs and UI)
that turns the glucose data of another integration (Nightscout, Dexcom, …)
into optional alarms, reminders and reports. One config entry (and one
service device) per person.

**Secondary by design.** It is not a medical device and never the primary
alarm. Every user-facing place that matters (README top, setup dialog with a
mandatory confirmation, options, documentation site) carries a prominent
disclaimer: it does not replace the alarms of the CGM, pump or medical app.
Keep it that way.

## Principles and decisions

- **Nothing is guessed.** No reading time → no glucose alarms (a repair issue
  says so), never a `last_changed` fallback. Sensors without a unit are only
  read once the user set the unit. Thresholds come only from entities
  (Nightscout threshold sensors or an `input_number`), never from fixed values
  or own number entities.
- **Source data belongs to the source integration:** no own status/trend/rate/
  data-age sensors of the source; dedicated source sensors win, attributes of
  the glucose sensor (`direction`, `delta`, `date`) are the fallback.
- **The integration decides *when*, the user decides *how*.** Notifications
  are the user's own automations on the **event entities**: one per enabled
  alarm (`<alarm>_alert`, `<alarm>_ended`, `<change>_soon`) and one for the
  report (`report`). Event types are unique per person, so a device target
  works. Event data are entity attributes (`trigger.to_state.attributes`).
  No device triggers, no action fields in the options, no shipped scripts.
- **Repo ships only the generic mechanism.** Personal outputs (specific
  displays, phones, the maintainer's scripts) never go into the repository.
- **Inform, don't block.** Duplicates (e.g. the same glucose sensor in two
  entries) get a plain notice, not an error. Acknowledgements are per entry
  and per alarm. No example texts that patronize users.
- **Every feature can be switched off.** Threshold alarms are on when a
  threshold entity is set, rapid alarms via detection (off/trend/rate), data
  loss is always on, change reminders when a wear duration is set, reports
  when a period entity is set. Numbers/times are "field or entity, entity
  wins". "Only when the person is at home" is an option per alarm (default
  off; a running alarm continues). The pause applies to all alarms except
  urgent low.
- **Robust alarms:** stale data neither starts nor ends glucose alarms;
  states survive restarts; after a snooze the alarm is re-checked.
- **No real health data** anywhere in the repo, tests or screenshots. Tests
  and demos use synthetic data and the names Alex/Sam.

## Layout

`custom_components/blood_glucose_monitor/`:

| Module | Purpose |
| --- | --- |
| `glucose.py`, `report.py` | Pure logic without Home Assistant (readings, trend parsing, report statistics) |
| `alarm.py` | Alarm state machine (idle/pending/active/snoozed), phases |
| `source.py` | Reads the source entities, unit conversion |
| `monitor.py` | `AlarmMonitor`: one per entry; drives the engines, timers, storage, event firing (`async_fire`) |
| `reports.py` | `ReportTracker`: periods of the report entity, statistics from the recorder |
| `event.py`, `sensor.py`, `button.py`, `switch.py` | Entities (`entity.py` is the base) |
| `links.py` | Prefilled automation builder link (device `configuration_url`, options menu) |
| `config_flow.py` | Setup (disclaimer → person → sources) and options menu (one step per alarm, report, pause) |
| `__init__.py` | Setup, actions `acknowledge` and `record_change` |

`site/` is the documentation site (static HTML/JS, no build): Information,
automation builder, documentation. `site/data.js` is the single source for
event types, their requirements and attributes; keep it in sync with the
code. `scripts/screenshots/` holds the demo Home Assistant used by the Pages
workflow to take screenshots.

## Documentation

After every change to behaviour, options, entities, events, attributes,
actions or texts, run the `docs-sync` agent (`.claude/agents/docs-sync.md`) so
`README.md`, `site/` (especially `site/data.js`) and the `CHANGELOG.md`
Unreleased section match the code. A change is not done before that.

## Conventions

- Target Home Assistant 2026.11+. Python 3.14 syntax (`except A, B:`),
  `import probatio as vol`.
- Code, entity names, UI texts and docs in English; German translations in
  `translations/de.json` must cover every key of `en.json`
  (`tests/test_translations.py` checks this).
- Translation keys of entities: `<alarm>_alarm` (sensor and event share the
  name), `acknowledge_<alarm>`, `<alarm>_changed`, `<alarm>_due`, `report`.
- Ruff for lint and format.

## Testing

Tests use `pytest-homeassistant-custom-component` and need Linux (Home
Assistant does not run on Windows): `scripts/test.sh` runs lint and tests in
Docker, or in a Linux venv with `requirements_test.txt`:

```bash
ruff check --fix . && ruff format . && python -m pytest -q -p no:logging
```

Scenario tests (`tests/test_alarms.py`: `Scenario`, `capture_fired`) drive
time with freezegun and record the events of the event entities. Await report
background tasks with `hass.async_block_till_done(wait_background_tasks=True)`.
Hassfest and the Marketplace validation run in GitHub Actions only.

## Branches and releases

- Work on `develop`; never push to `main` directly and never create tags.
- A release is a pull request `develop` → `main`, merged as a **merge commit**.
  `.github/workflows/release.yaml` checks the version, runs tests and
  validation and creates tag and GitHub release. The `/release` command
  (`.claude/commands/release.md`) prepares it: conventional commits, version
  in `manifest.json`, `CHANGELOG.md` (Keep a Changelog), `scripts/check_version.py --release`.
- Conventional commits: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`,
  `test:`; `BREAKING CHANGE` bumps the minor version while the major is 0.
- The Pages workflow deploys the site from `main`; on `develop` it only
  produces the screenshots as an artifact.
- Commit and push only when asked.
