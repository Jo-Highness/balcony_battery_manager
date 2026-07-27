"""Offline unit tests for the pure control logic (no Home Assistant needed).

Loads logic.py directly via importlib so the suite runs in a plain Python
container without installing Home Assistant.
"""
import importlib.util
import pathlib
import sys
from datetime import datetime, timedelta, timezone

_HERE = pathlib.Path(__file__).resolve().parent
_LOGIC = _HERE.parent / "custom_components" / "balcony_battery_manager" / "logic.py"
_spec = importlib.util.spec_from_file_location("bbm_logic", _LOGIC)
logic = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = logic  # dataclasses need the module registered
_spec.loader.exec_module(logic)


CFG = {
    "discharge_steps": [0.0, 350.0, 800.0],
    "discharge_thresholds": [800.0, 1600.0],
    "hysteresis": 100.0,
    "dwell_s": 600.0,
    "max_charge": 2500.0,
    "surplus_reserve": 100.0,
    "target_soc": 100.0,
    "capacity_kwh": 15.5,
    "pv_nominal_w": 2000.0,
    "afternoon_hour": 13,
    "afternoon_factor": 1.0 / 3.0,
}


# ---------------- corrected demand ----------------

def test_corrected_demand():
    # meter understates by the Solarbank feed-in; add it back
    assert logic.corrected_demand(600.0, 350.0) == 950.0


# ---------------- discharge staircase ----------------

def _run_discharge(demands_with_dt, cfg=CFG):
    st = logic.DischargeState()
    out = None
    for demand, dt in demands_with_dt:
        out = logic.update_discharge(
            st, demand, dt, cfg["discharge_steps"], cfg["discharge_thresholds"],
            cfg["hysteresis"], cfg["dwell_s"])
    return st, out


def test_discharge_needs_full_dwell():
    # D above th1 but not yet 10 min -> still 0
    st, w = _run_discharge([(1000, 300)])
    assert w == 0.0 and st.step_index == 0
    # after 10 min continuous -> stage 1
    st, w = _run_discharge([(1000, 300), (1000, 300)])
    assert w == 350.0


def test_discharge_high_demand_jumps_to_stage2():
    st, w = _run_discharge([(1700, 600)])
    assert w == 800.0 and st.step_index == 2


def test_discharge_timer_resets_when_candidate_changes():
    # 5 min at >1600 (candidate 2), then demand drops to 1000 (candidate 1)
    st, w = _run_discharge([(1700, 300), (1000, 300)])
    assert w == 0.0  # neither candidate held 10 min continuously
    # then hold 1000 for another 10 min -> stage 1
    st2 = logic.DischargeState()
    for d, dt in [(1700, 300), (1000, 300), (1000, 300)]:
        w = logic.update_discharge(st2, d, dt, CFG["discharge_steps"],
                                   CFG["discharge_thresholds"], CFG["hysteresis"], CFG["dwell_s"])
    assert w == 350.0


def test_discharge_downshift_one_step_with_hysteresis():
    st = logic.DischargeState(step_index=2)
    # demand drops below th2 - hyst = 1500 -> after dwell go one step down to 350
    for _ in range(2):
        w = logic.update_discharge(st, 1400, 300, CFG["discharge_steps"],
                                   CFG["discharge_thresholds"], CFG["hysteresis"], CFG["dwell_s"])
    assert w == 350.0 and st.step_index == 1


def test_discharge_hysteresis_holds_stage():
    st = logic.DischargeState(step_index=2)
    # demand at 1550 (between th2-hyst=1500 and th2=1600) -> stays at stage 2
    for _ in range(5):
        w = logic.update_discharge(st, 1550, 300, CFG["discharge_steps"],
                                   CFG["discharge_thresholds"], CFG["hysteresis"], CFG["dwell_s"])
    assert w == 800.0


# ---------------- predictive charging ----------------

def test_rest_pv_energy_afternoon_cap():
    now = datetime(2026, 7, 1, 14, 0, tzinfo=timezone.utc)
    sunset = datetime(2026, 7, 1, 17, 0, tzinfo=timezone.utc)  # 3 h
    # current pv 1500 but afternoon cap = 2000/3 ~ 667 -> ~667 * 3h = ~2000 Wh
    wh = logic.rest_pv_energy_wh(now, sunset, 1500, 2000, 13, 1/3, step_min=5)
    assert 1900 < wh < 2100


def test_charge_need_wh():
    assert logic.charge_need_wh(90, 100, 15.5) == 1550.0  # 10% of 15.5 kWh


def test_charge_release_deficit():
    now = datetime(2026, 7, 1, 16, 0, tzinfo=timezone.utc)
    sunset = datetime(2026, 7, 1, 17, 0, tzinfo=timezone.utc)  # 1 h left
    # low pv, big gap -> deficit -> release
    rel, need, rest = logic.charge_release(
        now, sunset, soc=50, p_anker_pv=100, target_soc=100,
        capacity_kwh=15.5, nominal_w=2000, afternoon_hour=13, afternoon_factor=1/3)
    assert rel is True and need > rest


def test_charge_release_pv_sufficient():
    now = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
    sunset = datetime(2026, 7, 1, 20, 0, tzinfo=timezone.utc)  # 10 h, morning full cap
    rel, need, rest = logic.charge_release(
        now, sunset, soc=95, p_anker_pv=1800, target_soc=100,
        capacity_kwh=15.5, nominal_w=2000, afternoon_hour=13, afternoon_factor=1/3)
    assert rel is False  # plenty of PV to reach 100%


def test_charge_power_closed_loop():
    # exporting 800, reserve 100 -> raise charge by 700
    assert logic.charge_power(0, 800, reserve=100, max_charge=2500) == 700
    # export gone -> lower charge back towards 0
    assert logic.charge_power(700, 0, reserve=100, max_charge=2500) == 600
    # never exceed max
    assert logic.charge_power(2400, 800, reserve=100, max_charge=2500) == 2500
    # never below 0 (would pull from grid)
    assert logic.charge_power(0, -50, reserve=100, max_charge=2500) == 0


# ---------------- coordination ----------------

def _state():
    return logic.ControllerState()


def test_decide_discharge_priority_over_charge():
    st = _state()
    st.discharge.step_index = 2  # already feeding 800
    now = datetime(2026, 7, 1, 16, 0, tzinfo=timezone.utc)
    sunset = now + timedelta(hours=1)
    dec = logic.decide(st, now=now, sunset=sunset, p_batt_draw=1700, p_anker_out=0,
                       grid_export=500, soc=50, p_anker_pv=100, dt_s=30, cfg=CFG)
    assert dec.mode == logic.MODE_DISCHARGE and dec.grid_flow == "discharge"
    assert dec.target_power == 800


def test_decide_charge_when_deficit_and_surplus():
    st = _state()
    now = datetime(2026, 7, 1, 16, 0, tzinfo=timezone.utc)
    sunset = now + timedelta(hours=1)
    dec = logic.decide(st, now=now, sunset=sunset, p_batt_draw=0, p_anker_out=0,
                       grid_export=900, soc=50, p_anker_pv=50, dt_s=30, cfg=CFG)
    assert dec.mode == logic.MODE_CHARGE and dec.grid_flow == "charge"
    assert dec.target_power == 800  # 900 - reserve 100


def test_decide_idle_when_pv_sufficient():
    st = _state()
    now = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
    sunset = now + timedelta(hours=10)
    dec = logic.decide(st, now=now, sunset=sunset, p_batt_draw=0, p_anker_out=0,
                       grid_export=900, soc=95, p_anker_pv=1800, dt_s=30, cfg=CFG)
    assert dec.mode == logic.MODE_IDLE and dec.target_power == 0


def test_decide_charge_ramps_down_when_surplus_shrinks():
    st = _state()
    now = datetime(2026, 7, 1, 16, 0, tzinfo=timezone.utc)
    sunset = now + timedelta(hours=1)
    d1 = logic.decide(st, now=now, sunset=sunset, p_batt_draw=0, p_anker_out=0,
                      grid_export=900, soc=50, p_anker_pv=50, dt_s=30, cfg=CFG)
    # surplus disappears -> next cycle charge power drops
    d2 = logic.decide(st, now=now, sunset=sunset, p_batt_draw=0, p_anker_out=0,
                      grid_export=0, soc=50, p_anker_pv=50, dt_s=30, cfg=CFG)
    assert d2.target_power < d1.target_power


def test_failsafe_zero():
    dec = logic.failsafe_decision()
    assert dec.mode == logic.MODE_FAILSAFE
    assert dec.target_power == 0 and dec.grid_flow == ""


def test_clamp():
    assert logic.clamp(1200, 0, 800) == 800
    assert logic.clamp(-5, 0, 800) == 0
    assert logic.clamp(400, 0, 800) == 400
