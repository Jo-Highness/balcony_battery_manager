# Security Policy

## Supported versions

Only the **latest released version** of Balcony Battery Manager receives security
fixes. Please update to the newest release before reporting an issue, and always
run the latest version in production.

| Version        | Supported          |
| -------------- | ------------------ |
| Latest release | :white_check_mark: |
| Older releases | :x:                |

## Reporting a vulnerability

Please report suspected vulnerabilities **privately** through GitHub Security
Advisories:

1. Go to the repository's **Security** tab.
2. Choose **Report a vulnerability** (Private vulnerability reporting).
3. Provide a clear description, affected version, and reproduction steps.

Please do **not** open a public issue for security reports.

## Scope and threat model

Balcony Battery Manager is a Home Assistant custom integration with a small
attack surface:

- It uses **no cloud services and no API credentials** of its own.
- It stores **no secrets**.
- It only reads from, and writes to, **local Home Assistant entities that the
  user explicitly configured** (power/SoC sensors as inputs, and the Solarbank
  actor `select`/`number` entities as outputs).

Actions the integration performs are therefore bounded by the entities the user
selected and by Home Assistant's own permission model. There is no external
network communication introduced by this integration.
