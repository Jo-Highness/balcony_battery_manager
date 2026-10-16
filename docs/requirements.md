# Requirements — Balcony Battery Manager v2

Concise, code-independent requirements for the v2 line (Anker SOLIX Solarbank 4).
Version 2.2 · last updated 2026-10-16. The v1 line (Solarbank 3) is superseded
and not described here.

## 1. Purpose and scope

A Home Assistant custom integration (domain `balcony_battery_manager`) that
controls an Anker SOLIX Solarbank 4 (E5000 Pro) next to an existing house PV
system with a main battery:

- relieve the main battery when the house demand is high,
- charge the Solarbank from PV surplus when PV alone will not reach the target
  state of charge by sunset,
- cover the house from the Solarbank when the main battery is empty.

**In scope:** a cyclic controller reading Home Assistant entities and writing to
the Solarbank's *Third-Party Control* entities via standard services; UI
configuration; safety behaviour.
**Out of scope:** any cloud/vendor API (a separate Anker Solix integration
provides the entities), controlling the main PV system, external forecasts.

## 2. Interfaces

| Kind | Entity | Unit / values |
|---|---|---|
| Input (required) | Main-battery power (signed, sign flag) | W, kW or MW |
| Input (required) | Grid power (signed, sign flag) | W, kW or MW |
| Input (required) | Solarbank AC output, Solarbank PV power | W, kW or MW |
| Input (required) | Solarbank state of charge | % |
| Input (optional) | Main-battery state of charge (enables grid support) | % |
| Input (optional) | Sun entity (next sunset) | `next_setting` |
| Output (required) | Grid-flow select | user-configured "discharge" / "charge" options |
| Output (required) | Target grid power number | W or kW, device min/max |
| Output (optional) | Operating-mode select | user-configured control / restore options |

All calculations are done in watts, percent and kWh.

## 3. Functional requirements

- **FR-1 Inputs.** Values are converted by `unit_of_measurement`. A missing unit
  is taken as the base unit (W / %); an unsupported unit makes the sensor
  unavailable and is logged once.
- **FR-2 Corrected demand.** `D = main-battery draw + Solarbank output`. All
  discharge thresholds are evaluated against D.
- **FR-3 Mode arbitration.** Exactly one mode per cycle, in priority order:
  `grid_support` > `discharge` > `charge` > `idle`; plus `failsafe` and
  `disabled`.
- **FR-4 Discharge staircase.** Steps 0 / stage 1 / stage 2 with thresholds
  TH1 < TH2. Each threshold has an independent "continuously above" and
  "continuously below (threshold − hysteresis)" timer. Upshift (may skip a step)
  after the dwell time above a threshold; downshift by one step after the dwell
  time below.
- **FR-5 Predictive charging.** Remaining PV energy until sunset is estimated
  from the live PV power, capped at the PV nominal power and, from the afternoon
  boundary hour (local time), at nominal × afternoon factor. Charging is released
  only if remaining PV < energy needed to reach the target SoC. Charge power is
  a closed loop `clamp(previous + (export − reserve), 0, max_charge)`.
- **FR-6 Grid support.** Active while the main-battery SoC ≤ "empty" (released
  above empty + hysteresis). Feed-in is a closed loop
  `clamp(previous + (main-battery draw + grid import − margin), 0, max)`.
- **FR-7 Minimum SoC.** No discharge mode runs while the Solarbank SoC ≤
  minimum SoC; the staircase is reset.
- **FR-8 Entities.** Mode (enum), target power, corrected demand, surplus
  (W, measurement) and the master switch *Enabled*, whose state persists across
  restarts.
- **FR-9 Actions.** `enable`, `disable`, `recalculate_now`, each with an
  optional `config_entry_id`.
- **FR-10 Configuration.** UI config and options flow (sectioned, with help
  texts), validation of threshold order, select options and units; optional
  fields can be cleared; unambiguous-only prefill.

## 4. Safety requirements

- **S-1 Fail-safe.** A missing/invalid required sensor → target power 0 W and
  controller state reset.
- **S-2 Write order.** Changing direction: power 0 W → switch the grid-flow
  select → new setpoint.
- **S-3 Confirmed writes.** Every actuator write is awaited with a timeout; a
  failure or timeout falls back to 0 W.
- **S-4 Limits.** Setpoints are clamped to the number's min/max; closed loops
  are capped at the device maximum and re-anchored on the power actually in
  effect (no integrator wind-up).
- **S-5 Disable.** Disabling holds the control lock, writes 0 W and, if
  configured, restores the operating mode; no later cycle writes a non-zero
  setpoint while disabled. Unloading the entry writes 0 W.
- **S-6 Single controller.** Only one config entry may drive a given set of
  actuators.
- **S-7 No grid charging.** Charging only absorbs measured export above the
  reserve.

## 5. Non-functional requirements

- **NFR-1** Only standard Home Assistant services (`number.set_value`,
  `select.select_option`, also `input_*`); no vendor internals.
- **NFR-2** Local only, no external servers; async, non-blocking.
- **NFR-3** Control interval configurable (5–600 s, default 30 s); deadband
  avoids redundant writes.
- **NFR-4** HACS and hassfest compliant; translations en/de complete.
- **NFR-5** Behaviour changes are covered by automated tests.

## 6. Acceptance criteria

- **A-1** A kW sensor value of 1.5 is processed as 1500 W.
- **A-2** Switching from charge to discharge produces the write sequence
  0 W → select → setpoint.
- **A-3** At Solarbank SoC ≤ minimum no discharge setpoint is written.
- **A-4** With a device maximum of 800 W the charge integrator never exceeds
  800 W.
- **A-5** After `disable` the number is at 0 W and no further non-zero write
  happens.
- **A-6** Setpoint changes below the deadband are not written.
- **A-7** A cleared optional field is removed from the configuration.

## 7. Assumptions

- One controllable Solarbank per config entry; the Solarbank is in Third-Party
  Control mode.
- The main system provides reliable power sensors; the main-battery SoC is
  optional (without it grid support is off).
- On the Solarbank 4 the third-party discharge setpoint is limited to about
  800 W by the device.
