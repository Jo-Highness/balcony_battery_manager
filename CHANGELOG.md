# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- Added a wind-up cap to the discharge staged control to prevent the target
  power from accumulating beyond the usable range.

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

[Unreleased]: https://github.com/Jo-Highness/balcony_battery_manager/compare/v2.1.2...HEAD
[2.1.2]: https://github.com/Jo-Highness/balcony_battery_manager/compare/v2.1.1...v2.1.2
[2.1.1]: https://github.com/Jo-Highness/balcony_battery_manager/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/Jo-Highness/balcony_battery_manager/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/Jo-Highness/balcony_battery_manager/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/Jo-Highness/balcony_battery_manager/releases/tag/v1.0.0
