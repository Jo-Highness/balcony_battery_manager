"""Pure control logic for Balcony Battery Manager (no Home Assistant imports).

Everything here is deterministic and unit-testable without a running HA. The
coordinator feeds live measurements + config in and applies the returned
setpoints to the Solarbank actor entities.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

# Discharge modes decided each cycle.
MODE_IDLE = "idle"
MODE_DISCHARGE = "discharge"
MODE_CHARGE = "charge"
MODE_FAILSAFE = "failsafe"


def clamp(value: float, low: float, high: float) -> float:
    """Clamp value into [low, high]."""
    return max(low, min(high, value))


def corrected_demand(p_batt_draw: float, p_anker_out: float) -> float:
    """Corrected main-battery demand D = P_batt_draw + P_anker_out.

    The house energy meter understates the main-battery draw because the
    Solarbank feed-in is already subtracted. Adding the current Solarbank
    output back yields the *actual* demand D, which is independent of our own
    feed-in setpoint. All discharge thresholds are evaluated against D.
    """
    return p_batt_draw + p_anker_out


@dataclass
class DischargeState:
    """Persistent state of the discharge staircase controller."""

    step_index: int = 0          # index into `steps` (0 = off)
    candidate: int | None = None  # index we are currently dwelling towards
    elapsed_s: float = 0.0        # seconds the candidate has held continuously


def _target_index(demand: float, cur: int, thresholds: list[float],
                  hysteresis: float) -> int:
    """Instantaneous target step index from demand, with hysteresis.

    Upshifts may jump multiple steps (e.g. D above the top threshold goes
    straight to the highest step). Downshifts move at most one step at a time
    and only once demand falls below (threshold - hysteresis).

    thresholds ascending, len == number of steps - 1. thresholds[i] is the
    demand above which step i+1 becomes active.
    """
    # Highest step whose ON threshold is exceeded (upshift may jump).
    up = 0
    for i, th in enumerate(thresholds):
        if demand > th:
            up = i + 1
    if up > cur:
        return up
    # Downshift: leave the current step only below (threshold - hysteresis),
    # and only one step at a time.
    if cur > 0 and demand < thresholds[cur - 1] - hysteresis:
        return cur - 1
    return cur


def update_discharge(state: DischargeState, demand: float, dt_s: float,
                     steps: list[int], thresholds: list[float],
                     hysteresis: float, dwell_s: float) -> int:
    """Advance the staircase controller by dt_s seconds; return step power (W).

    A step change is only committed after the candidate target has held
    continuously for `dwell_s` seconds (timer resets whenever the candidate
    changes). This gives the "condition must hold for >= 10 min" behaviour with
    a per-transition timer.
    """
    target = _target_index(demand, state.step_index, thresholds, hysteresis)
    if target == state.step_index:
        state.candidate = None
        state.elapsed_s = 0.0
    else:
        if state.candidate == target:
            state.elapsed_s += dt_s
        else:
            state.candidate = target
            state.elapsed_s = dt_s
        if state.elapsed_s >= dwell_s:
            state.step_index = target
            state.candidate = None
            state.elapsed_s = 0.0
    return steps[state.step_index]


def rest_pv_energy_wh(now: datetime, sunset: datetime, p_anker_pv: float,
                      nominal_w: float, afternoon_hour: int,
                      afternoon_factor: float, step_min: int = 5) -> float:
    """Estimate remaining Solarbank PV energy (Wh) from now until sunset.

    Heuristic from live power only (no external forecast): expected power at a
    given time = min(current P_anker_pv, cap), where cap = nominal_w before the
    afternoon boundary and nominal_w * afternoon_factor from it on. Integrated
    in small steps up to sunset.
    """
    if sunset <= now:
        return 0.0
    total = 0.0
    t = now
    step = timedelta(minutes=step_min)
    hours = step_min / 60.0
    while t < sunset:
        cap = nominal_w if t.hour < afternoon_hour else nominal_w * afternoon_factor
        total += min(max(p_anker_pv, 0.0), cap) * hours
        t += step
    return total


def charge_need_wh(soc: float, target_soc: float, capacity_kwh: float) -> float:
    """Energy (Wh) needed to reach target_soc from soc."""
    return max(0.0, (target_soc - soc)) / 100.0 * capacity_kwh * 1000.0


def charge_release(now: datetime, sunset: datetime, soc: float, p_anker_pv: float,
                   *, target_soc: float, capacity_kwh: float, nominal_w: float,
                   afternoon_hour: int, afternoon_factor: float) -> tuple[bool, float, float]:
    """Predictive charge gate. Returns (release, need_wh, rest_pv_wh).

    Release charging from house surplus only if the estimated remaining PV
    energy is smaller than the energy needed to hit the target SoC by sunset.
    """
    need = charge_need_wh(soc, target_soc, capacity_kwh)
    rest = rest_pv_energy_wh(now, sunset, p_anker_pv, nominal_w,
                             afternoon_hour, afternoon_factor)
    return (rest < need and need > 0.0), need, rest


def charge_power(prev_charge: float, grid_export: float, *, reserve: float,
                 max_charge: float) -> float:
    """Closed-loop charge power from live export surplus.

    grid_export is the *live* export (positive = exporting). We nudge the
    charge power so the export settles at ~reserve: raise charge while there is
    export above the reserve, lower it as export shrinks. Strictly bounded to
    [0, max_charge] so we never pull from grid or the main battery.
    """
    return clamp(prev_charge + (grid_export - reserve), 0.0, max_charge)


@dataclass
class Decision:
    """Result of one coordination cycle."""

    mode: str
    grid_flow: str            # "discharge" | "charge" | "" (idle)
    target_power: float       # W for number.target_grid_power
    demand: float = 0.0
    surplus: float = 0.0
    charge_release: bool = False
    need_wh: float = 0.0
    rest_pv_wh: float = 0.0
    reason: str = ""


@dataclass
class ControllerState:
    """Full persistent controller state (owned by the coordinator)."""

    discharge: DischargeState = field(default_factory=DischargeState)
    last_charge_w: float = 0.0


def decide(state: ControllerState, *, now: datetime, sunset: datetime,
           p_batt_draw: float, p_anker_out: float, grid_export: float,
           soc: float, p_anker_pv: float, dt_s: float, cfg: dict) -> Decision:
    """Single coordination cycle: pick exactly one mode and its setpoint.

    Priority: discharge support (high demand) before charging. All setpoints
    are clamped to the device limits by the caller. `cfg` carries the tunable
    parameters (see const.DEFAULTS).
    """
    demand = corrected_demand(p_batt_draw, p_anker_out)

    # --- Discharge staircase (evaluated against corrected demand D) ---
    step_w = update_discharge(
        state.discharge, demand, dt_s,
        steps=cfg["discharge_steps"], thresholds=cfg["discharge_thresholds"],
        hysteresis=cfg["hysteresis"], dwell_s=cfg["dwell_s"],
    )

    if step_w > 0:
        # Discharging wins; do not accumulate charge power.
        state.last_charge_w = 0.0
        return Decision(mode=MODE_DISCHARGE, grid_flow="discharge",
                        target_power=step_w, demand=demand,
                        reason=f"D={demand:.0f}W -> Stufe {step_w:.0f}W")

    # --- Predictive PV-surplus charging ---
    release, need_wh, rest_wh = charge_release(
        now, sunset, soc, p_anker_pv,
        target_soc=cfg["target_soc"], capacity_kwh=cfg["capacity_kwh"],
        nominal_w=cfg["pv_nominal_w"], afternoon_hour=cfg["afternoon_hour"],
        afternoon_factor=cfg["afternoon_factor"],
    )
    if release:
        c = charge_power(state.last_charge_w, grid_export,
                         reserve=cfg["surplus_reserve"], max_charge=cfg["max_charge"])
        state.last_charge_w = c
        if c > 0:
            return Decision(mode=MODE_CHARGE, grid_flow="charge", target_power=c,
                            demand=demand, surplus=grid_export, charge_release=True,
                            need_wh=need_wh, rest_pv_wh=rest_wh,
                            reason=f"Defizit {need_wh - rest_wh:.0f}Wh, laden {c:.0f}W")
        # Deficit exists but currently no surplus -> hold at 0 (still charge mode intent)
        return Decision(mode=MODE_IDLE, grid_flow="", target_power=0.0,
                        demand=demand, surplus=grid_export, charge_release=True,
                        need_wh=need_wh, rest_pv_wh=rest_wh,
                        reason="Defizit, aber kein Ueberschuss")

    state.last_charge_w = 0.0
    return Decision(mode=MODE_IDLE, grid_flow="", target_power=0.0, demand=demand,
                    surplus=grid_export, need_wh=need_wh, rest_pv_wh=rest_wh,
                    reason="Leerlauf (PV deckt Bedarf)")


def failsafe_decision(demand: float = 0.0) -> Decision:
    """Sensor outage -> feed-in AND charging to 0."""
    return Decision(mode=MODE_FAILSAFE, grid_flow="", target_power=0.0,
                    demand=demand, reason="Fail-safe: Sensor unavailable -> 0W")
