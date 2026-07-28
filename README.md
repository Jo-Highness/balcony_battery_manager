# Balcony Battery Manager

A Home Assistant custom integration that turns an **Anker SOLIX Solarbank 4
(E5000 Pro)** into a demand-aware home battery controller. It watches your
house's power flows and, every cycle, decides exactly one action: **feed the
house from the Solarbank** to relieve your main battery when demand is high, or
**charge the Solarbank strictly from PV surplus** so you never pull charge power
from the grid or the main battery.

The Solarbank 4 must be controllable from Home Assistant through the official
Anker integration (`anker_solix_official`) with its operating mode set to
**Third-Party Control**. The controller then drives two of its entities:
- a **select** for the grid-flow direction (`charge` / `discharge`), and
- a **number** for the target grid power (0–3000 W).

Every parameter and every entity is configurable from the Home Assistant UI
(config flow + options flow); nothing is hard-coded to one installation.

---

## What it actually does

### The corrected demand `D` (the key idea)
Your energy meter *understates* how much the house pulls from the main battery,
because the Solarbank's feed-in has already been subtracted from that reading.
So the controller reconstructs the **true demand**:

```
D = P_batt_draw + P_anker_out
```

`D` is independent of the Solarbank's own feed-in setpoint (no feedback loop),
and **all discharge thresholds are evaluated against `D`**.

### Discharge support (relieve the main battery) — a staircase
A hysteresis staircase with configurable steps (default **0 / 350 / 800 W**):
- `D` above **1600 W** continuously for **≥ 10 min** → feed **800 W**.
- `D` above **800 W** continuously for **≥ 10 min** → feed at least **350 W**.
- `D` below *(threshold − hysteresis)* for **≥ 10 min** → step **one** level down.

Each transition has its own dwell timer: the condition must hold *continuously*
for the dwell time, and a configurable hysteresis band (default 100 W) prevents
flapping. Upshifts may jump straight to the top step; downshifts move one step
at a time.

### Charge from PV surplus — predictive, closed-loop
Charging is only released when the Solarbank won't reach its target on its own:

1. **Remaining PV estimate** until sunset (heuristic from live power, *no*
   external forecast): expected power = `min(current PV, cap)`, where `cap` is
   the PV nominal power, dropping to **1/3** of nominal from a configurable
   afternoon boundary (default **13:00**). Integrated in small steps up to
   sunset (from `sun.sun`).
2. **Energy need** = `(target SoC − current SoC)/100 × capacity`.
3. If the estimated remaining PV energy is **less** than the need → **deficit**
   → charging from surplus is released to cover it by sunset. Otherwise the PV
   is expected to suffice and no grid-surplus charging happens.

When charging is released the power is regulated in a **closed loop on the live
export**:

```
charge_power = clamp(previous + (live_export − reserve), 0, max_charge)
```

so the export settles at the reserve (default 100 W) and the charge power is
bounded to `[0, max_charge]` (default 2500 W). Because charging itself lowers the
export in real time, the loop continually re-tunes; if the surplus vanishes,
charging ramps down to 0. **It never charges from the grid or the main battery.**

### Grid support — main battery empty
When the **main house battery is empty** (its SoC at/below a threshold, default
10 %) and the Solarbank still has charge, the Solarbank steps in to cover the
house: a closed loop on the live grid meter keeps the residual **grid import at
a small margin** (default 100 W). In other words the Solarbank feeds *the house
demand minus ~100 W*, so almost everything comes from the Solarbank and only
~100 W is drawn from the grid. This mirrors the charge loop (which keeps the
*export* at the reserve) and automatically accounts for any PV or remaining main
contribution. Requires a **main-battery SoC** entity to be configured; without
it, grid support stays off. Uses a SoC hysteresis (default 3 %) to release.

### Coordination & fail-safe
One coordinator decides a single mode per cycle. Priority: **grid support**
(main battery empty) → **discharge support** (high `D`) → **charging** → idle.
Every setpoint is clamped to the device limits. If any required sensor becomes
unavailable, both feed-in **and** charging are set to **0** (fail-safe).

> **Sign conventions:** each signed input has a "positive =" toggle. For an
> **E3DC/KNX** meter (negative = discharge into house / export) the auto-prefill
> sets both `batt_draw_positive` and `grid_export_positive` to **off** — leave
> them off, otherwise the corrected demand `D` comes out negated and nothing is
> fed in.

---

## Configurable parameters (with defaults)

| Parameter | Default |
|---|---|
| Discharge thresholds | 800 W / 1600 W |
| Discharge stages | 350 W / 800 W |
| Dwell time | 10 min |
| Hysteresis | 100 W |
| Max charge power | 2500 W |
| Surplus reserve | 100 W |
| Target SoC | 100 % |
| Battery capacity | 15.5 kWh (auto-detected from the Solarbank sensor) |
| PV nominal power | 2000 W |
| Afternoon cap factor / boundary | 1/3 · nominal, from 13:00 |
| Coordinator interval | 30 s |
| Write deadband | 25 W |
| Sign conventions | grid-export-positive, batt-draw-positive (per sensor) |

Sunset target time comes from `sun.sun`.

## Diagnostic entities
- `switch.*_enabled` — master switch for the control loop.
- `sensor.*_mode` — `idle` / `discharge` / `charge` / `failsafe` (+ attributes:
  grid flow, charge release, energy need, remaining PV, human-readable reason).
- `sensor.*_target_power`, `sensor.*_corrected_demand`, `sensor.*_surplus`.

Services: `balcony_battery_manager.enable`, `.disable`, `.recalculate_now`.

---

## ⚠️ BREAKING CHANGE — v2.0.0

**v2 is a full rewrite for the Solarbank 4 and is NOT compatible with v1
(Solarbank 3).** The actor model changed (single grid-flow select + target-power
number instead of usage-mode/output-preset/AC-charge switch) and the option set
is entirely different. There is **no automatic migration**: on upgrade the old
config entry is rejected (`async_migrate_entry` returns `False`, logged as a
migration error).

**To upgrade:** remove the old *Balcony Battery Manager* integration entry and
add it again. Entities are auto-suggested for common setups (Anker
`anker_solix_official` Solarbank 4 + E3DC/KNX meters + `sun.sun`); review and
adjust the suggestions, then save.

## Installation (HACS)
Add this repository as a custom repository (category *Integration*), install,
restart Home Assistant, then **Settings → Devices & Services → Add Integration →
Balcony Battery Manager**.

## Requirements
- Home Assistant 2024.12 or newer.
- Anker SOLIX Solarbank 4 exposed via `anker_solix_official` in **Third-Party
  Control** mode (grid-flow select + target-grid-power number available).
