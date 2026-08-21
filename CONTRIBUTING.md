# Contributing

Thanks for your interest in improving **Balcony Battery Manager**! This document
describes how to set up a development environment, run the checks, and submit
changes.

> [!IMPORTANT]
> This integration drives **real hardware** (an Anker SOLIX Solarbank via the
> `anker_solix_official` integration). Any change that alters control behaviour
> — discharge staging, thresholds, timers, charge logic, sign handling — **must
> come with tests** that pin the new behaviour. Untested behaviour changes will
> not be merged.

## Repository layout

```
balcony_battery_manager/
├── custom_components/
│   └── balcony_battery_manager/   # the integration source
│       ├── __init__.py            # setup / unload
│       ├── config_flow.py         # UI config flow + prefill
│       ├── coordinator.py         # control logic (discharge staging, charging)
│       ├── const.py
│       ├── manifest.json
│       └── ...
├── tests/                         # pytest suite
├── CHANGELOG.md
├── hacs.json
└── README.md
```

## Development environment

Use a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install ruff pytest pytest-homeassistant-custom-component
```

`pytest-homeassistant-custom-component` pulls in a matching Home Assistant
version and the test fixtures the suite relies on.

## Running the checks

Before opening a pull request, run all of the following and make sure they pass:

```bash
# Lint
ruff check .

# Formatting (check only — does not modify files)
ruff format --check .

# Tests
pytest
```

To auto-fix formatting locally, run `ruff format .` (without `--check`).

The same checks run in CI (the `Validate` and `Test` GitHub Actions workflows),
so green locally means green on the pull request.

## Commit messages

This project uses [Conventional Commits](https://www.conventionalcommits.org/).
Examples:

- `feat(coordinator): predictive PV-surplus charging`
- `fix(discharge): independent per-threshold timers`
- `docs: document config-flow prefill`
- `test(config-flow): cover E3DC sign prefill`
- `ci: add hassfest validation`

Breaking changes use a `!` (e.g. `feat(coordinator)!: ...`) and/or a
`BREAKING CHANGE:` footer. Commit types feed the release notes, so keep them
accurate.

## Pull request process

1. Fork the repository and create a feature branch off `main`.
2. Make your change, adding or updating tests for any behaviour change.
3. Run `ruff check .`, `ruff format --check .`, and `pytest` locally.
4. Update `CHANGELOG.md` under the `## [Unreleased]` section.
5. Open a pull request against `main`, filling in the pull-request template.
6. Ensure the CI checks pass; address review feedback.

By contributing you agree that your contributions are licensed under the same
license as this project (see `LICENSE`).
