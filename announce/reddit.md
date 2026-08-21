**Balcony Battery Manager — local HA control for an Anker SOLIX Solarbank 4 (E5000 Pro)**

Repo: https://github.com/Jo-Highness/balcony_battery_manager · v2.1.2 · MIT · min HA 2024.12 · EN/DE

<!-- IMAGE: dashboard card with the Mode sensor + power sensors. Insert a PNG. -->

Sharing a custom integration I run at home. It manages an Anker SOLIX Solarbank 4 balcony battery from Home Assistant — **no Anker cloud, no API key, all local and entity-driven.**

It reads live signals (battery draw, Solarbank output, grid power, SoC, PV, optional house-battery SoC, sun), decides a mode each cycle (idle / discharge / charge / failsafe), and writes setpoints to the Solarbank's third-party-control actor entities — a grid-flow **select** and a target-grid-power **number** — that a **separate Anker Solix integration has to provide.**

Logic: two-step discharge staircase with dwell + hysteresis, predictive PV-surplus charging, grid-support when the house battery is empty, a deadband, and fail-safe to 0 W.

UI config flow with vendor-aware prefill; all params editable later via Options. Adds Mode / Target power / Corrected demand / Surplus power sensors, an Enabled switch, and enable/disable/recalculate_now services. Install via HACS (custom repository for now).

<!-- GIF: a discharge step — Mode flips, target power changes, grid sensor responds. Insert a GIF. -->

**Limitations, honestly:**
- Drives real hardware — correct sign conventions and entity selection matter.
- Needs a separate Anker Solix integration for the actor entities.
- v2 is Solarbank-4 only (Solarbank-3 → v1 / re-add).
- Solarbank 4 target grid power tops out ~800 W for third-party discharge.

Feedback and issues welcome.
