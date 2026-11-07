# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Setup per person with a mandatory notice that this is not a medical device and does not replace the alarms of a CGM, pump or medical app
- Glucose sensor, optional person, and optional trend, change and reading time sensors, suggested from the same device as the glucose sensor
- Fallback to the `direction`, `delta` and `date` attributes of the glucose sensor (Nightscout)
- Notice when another entry already monitors the selected glucose sensor
- Options to change the sensors later
- Diagnostics download showing how the glucose data is read
- English and German translations
