# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.2.0] - 2026-10-16

### Fixed
- **Units:** power sensors in kW/MW were read as W (factor 1000 off). Values are
  now converted by `unit_of_measurement`; an unsupported unit is treated as
  unavailable (fail-safe) and logged once.
- **Actuator write order:** a direction change now sets the power to 0 W, then
  switches the grid-flow select, then writes the new setpoint. All writes are
  awaited with a timeout; a failed or timed-out write falls back to 0 W.
- **Minimum SoC:** the discharge staircase now respects *Minimum Solarbank SoC*
  as well (before, only grid support did).
- **Integrator wind-up:** the charge and grid-support loops are capped at the
  target number's maximum and frozen while the deadband skips a write or a write
  fails.
- **Disable:** takes the control lock, so no cycle can write a non-zero setpoint
  after disabling; the controller state is reset.
- Fail-safe now also resets the staircase timers.
- Clearing the optional main-battery SoC (or any optional field) in the options
  had no effect.
- The first control cycle integrated over the default instead of the configured
  interval.
- Without a sun entity the sunset is calculated from the Home Assistant location
  instead of a fixed 21:00 (still the last-resort fallback).
- The *Surplus* sensor showed 0 W while discharging.
- The `disable` action description promised to "restore the Anker mode", which
  did not exist — it is now implemented (see Added).

### Added
- Optional operating-mode select with *mode while controlling* and *mode when
  disabled*: disabling can hand control back to the Anker app automatically.
- Config-flow validation (threshold/stage order, select options, units) and help
  texts for every field (en/de); the form is split into sections.
- Duplicate protection: one entry per Solarbank (unique ID = target power number).
- Optional `config_entry_id` field for all actions.
- Diagnostics download; translated mode states; icons.
- Unloading/removing the entry leaves the Solarbank at 0 W.
- German README (`README.de.md`) and a concise v2 requirements document
  (`docs/requirements.md`).

### Changed
- **Minimum Home Assistant version is now 2025.2.0.**
- Settings are stored in the entry options (automatic migration to config entry
  version 2.2).
- Prefill is generic: it only suggests unambiguous matches (unit / device class,
  Anker platform) and no longer guesses sign conventions or vendor-specific
  entity names.
- Modernized to current Home Assistant patterns (`runtime_data`, actions
  registered at integration setup, service device, enum/measurement sensors).
  The *Enabled* switch is a regular control instead of a configuration entity.
- CI installs pinned test requirements and reports coverage.

### Removed
- `REQUIREMENTS.md` (mostly described v1) — replaced by `docs/requirements.md`.

## [2.1.4] - 2026-10-09

### Fixed
- The predictive charge gate evaluated the afternoon cap boundary (`afternoon_hour`)
  against the **UTC** hour instead of local time, shifting the cap by 1–2 h in
  Central Europe. The controller now works with local time.
- The master switch state was not persisted: after a Home Assistant restart or an
  options reload, a deliberately disabled controller silently re-enabled itself and
  started writing setpoints again. The state is now stored (removed with the entry).

### Changed
- The coordinator passes its config entry explicitly (HA 2024.11+ API, within the
  declared minimum of 2024.12).

## [2.1.3] - 2026-08-21

### Added
- GitHub Actions `Validate` workflow (HACS + hassfest) and `Test` workflow
  (ruff lint/format check and pytest) for continuous integration.
- Ruff configuration for linting and formatting.
- Unit tests covering the config flow, integration setup, and the coordinator.
- Repository meta files: `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`,
  issue forms (bug report / feature request), pull-request template,
  Dependabot configuration, and Release Drafter configuration/workflow.
- README screenshots (config flow, entities, dashboard) captured from a demo instance.

### Fixed
- The config flow crashed with an HTTP 500 (blank/unusable dialog) when
  auto-detection found no matching entities — i.e. on any install whose entity
  names differ from the author's. The setup form now renders regardless; a
  regression test covers it.

## [2.1.2] - 2026-08-16

### Fixed
- Grid support now covers the house from both battery discharge and grid draw
  when the main battery is empty, so the balcony battery no longer leaves the
  house on grid power unnecessarily.
- Lowered the default *maximum feed-in during grid support* to 800 W (the
  Solarbank's real limit) so the grid-support loop no longer winds up beyond
  what the device accepts.

## [2.1.1] - 2026-07-28

### Fixed
- Discharge staged control now uses independent per-threshold timers instead of
  resetting the candidate on every evaluation, avoiding premature step changes.

## [2.1.0] - 2026-07-28

### Added
- Grid support when the main battery is empty: the balcony battery steps in to
  cover the house rather than pulling from the grid.

### Fixed
- E3DC sign-prefill: correctly interpret the E3DC grid-power sign convention
  during config-flow prefill.

## [2.0.0] - 2026-07-27

### Changed
- **BREAKING:** Complete rewrite to control the **Anker SOLIX Solarbank 4 E5000
  Pro** via the `anker_solix_official` integration (Third-Party Control:
  `select` grid_flow + `number` target_grid_power). Discharge is governed by a
  D-corrected staged controller with predictive PV-surplus charging.
- Existing users must re-add the integration through the UI after upgrading;
  the previous Solarbank 3 configuration is not migrated.

### Removed
- Support for the Anker Solarbank 3 control model (superseded by the Solarbank 4
  actor entities).
- Automatic W/kW unit handling of the power sensors (all inputs were read as W;
  restored in 2.2.0).
- Energy-dashboard based prefill and AC-charge control via a `select` entity.

## [1.0.0] - 2026-06-03

### Added
- Initial release of the Balcony Battery Manager custom integration.
- Config flow with best-effort prefill from the energy dashboard and
  `anker_solix` entities.
- Support for both W and kW units across all power sensors.
- Optional `main_soc` input with vendor-aware prefill (E3DC / KNX and
  Solarbank).
- AC-charge power control via a `select` entity for chargers (such as the
  Solarbank 3) that expose no `number` entity.

[Unreleased]: https://github.com/Jo-Highness/balcony_battery_manager/compare/v2.2.0...HEAD
[2.2.0]: https://github.com/Jo-Highness/balcony_battery_manager/compare/v2.1.4...v2.2.0
[2.1.4]: https://github.com/Jo-Highness/balcony_battery_manager/compare/v2.1.3...v2.1.4
[2.1.3]: https://github.com/Jo-Highness/balcony_battery_manager/compare/v2.1.2...v2.1.3
[2.1.2]: https://github.com/Jo-Highness/balcony_battery_manager/compare/v2.1.1...v2.1.2
[2.1.1]: https://github.com/Jo-Highness/balcony_battery_manager/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/Jo-Highness/balcony_battery_manager/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/Jo-Highness/balcony_battery_manager/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/Jo-Highness/balcony_battery_manager/releases/tag/v1.0.0
