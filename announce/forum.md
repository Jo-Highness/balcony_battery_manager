# Balcony Battery Manager — control an Anker SOLIX Solarbank 4 (E5000 Pro) from Home Assistant

**Repo:** https://github.com/Jo-Highness/balcony_battery_manager
**Status:** v2.1.2 · MIT · min HA 2024.12 · translations: English + German

<!-- IMAGE: hero shot — the Mode sensor + a couple of the power sensors on a dashboard card.
     Insert a 1200px-wide PNG here. Suggested filename: docs/hero-dashboard.png -->

Hi everyone,

I'd like to share a small custom integration I built for my own setup and have been running for a while: **Balcony Battery Manager**. It manages an **Anker SOLIX Solarbank 4 (E5000 Pro)** plug-in/balcony battery from Home Assistant.

It does not talk to the Anker cloud and needs no API key. Everything is local and entity-driven: the integration reads live signals from Home Assistant, decides a mode each cycle, and writes setpoints to the Solarbank's **third-party-control actor entities** — a grid-flow **select** and a target-grid-power **number** — that a **separate Anker Solix integration must provide**. If those actor entities aren't present, this integration has nothing to write to.

## What it does

Each cycle it reads the signals you point it at — battery draw, Solarbank output, grid power, Solarbank SoC and PV, optionally a main house-battery SoC, and the sun — and picks one of four modes (**idle / discharge / charge / failsafe**), then writes the corresponding setpoints.

The control logic includes:

- **Two-step discharge staircase** with dwell time and hysteresis, so it settles instead of chasing every fluctuation.
- **Predictive PV-surplus charging** — uses PV/sun signals to charge from surplus rather than reacting only after the fact.
- **Grid-support step** when the main house battery is empty.
- **Deadband** around the target to avoid needless writes.
- **Fail-safe to 0 W** when inputs look wrong or unavailable.

## Setup and entities

- **UI config flow** with vendor-aware prefill; every parameter is editable later via **Options** — no YAML.
- **Sensors:** Mode (with diagnostic attributes), Target power, Corrected demand, Surplus power.
- **Switch:** an *Enabled* master switch.
- **Services:** `enable`, `disable`, `recalculate_now`.

<!-- IMAGE: the config-flow / options screen showing the prefilled entity pickers.
     Insert a PNG here. Suggested filename: docs/options-flow.png -->

<!-- GIF: short clip of a discharge step happening — Mode flips to "discharge", Target power
     changes, and the grid-power sensor responds. Keep it under ~10 s.
     Suggested filename: docs/discharge-step.gif -->

## Install

Via **HACS** as a custom repository. Once/if it's accepted into the default HACS store you'll be able to install it directly from there.

## Honest limitations

This drives real hardware, so please read before installing:

- It writes setpoints to a physical battery. **Correct sign conventions and entity selection matter** — pick the wrong entity or invert a sign and it will do the wrong thing. Start conservative and watch it.
- It **depends on a separate Anker Solix integration** to expose the third-party-control actor entities. No actors, no control.
- **v2 is Solarbank-4 only.** Solarbank-3 users should stay on v1 (or re-add on the older line); v2 is a breaking change.
- On the Solarbank 4, **target grid power for third-party discharge tops out around 800 W** — that's a hardware/firmware ceiling, not a config choice.

Feedback, issues, and corrections are welcome — especially from anyone running a different Solarbank 4 firmware. Thanks for reading.
