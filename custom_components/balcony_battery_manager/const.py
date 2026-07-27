"""Constants for the Balcony Battery Manager integration (v2, Solarbank 4)."""
from __future__ import annotations

DOMAIN = "balcony_battery_manager"

# Config-entry schema version. v1 (Solarbank 3) entries are NOT migratable;
# async_migrate_entry rejects them so the user re-adds the integration.
CONFIG_VERSION = 2

# ---------------------------------------------------------------------------
# Config / Options keys
# ---------------------------------------------------------------------------
# --- Input measurement entities ---
CONF_P_BATT_DRAW = "p_batt_draw"                 # main-battery draw into house
CONF_BATT_DRAW_POSITIVE = "batt_draw_positive"   # True: positive = discharge into house
CONF_P_ANKER_OUT = "p_anker_out"                 # Solarbank feed-in to house (W)
CONF_P_GRID = "p_grid"                           # grid power
CONF_GRID_EXPORT_POSITIVE = "grid_export_positive"  # True: positive = export
CONF_SOC_ANKER = "soc_anker"                     # Solarbank SoC (%)
CONF_P_ANKER_PV = "p_anker_pv"                   # Solarbank PV power (W)
CONF_SUN = "sun_entity"                          # sun.sun (sunset)

# --- Actor entities (from the Solix-4 integration) ---
CONF_GRID_FLOW_SELECT = "grid_flow_select"       # select: charge/discharge direction
CONF_GRID_FLOW_DISCHARGE = "grid_flow_discharge_option"  # option meaning "discharge"
CONF_GRID_FLOW_CHARGE = "grid_flow_charge_option"        # option meaning "charge"
CONF_TARGET_POWER_NUMBER = "target_power_number"  # number: target grid power (W)

# --- Discharge staircase ---
CONF_DISCHARGE_TH1 = "discharge_threshold_1"     # D above -> at least stage 1
CONF_DISCHARGE_TH2 = "discharge_threshold_2"     # D above -> stage 2
CONF_DISCHARGE_STAGE1 = "discharge_stage_1"      # feed-in W for stage 1
CONF_DISCHARGE_STAGE2 = "discharge_stage_2"      # feed-in W for stage 2
CONF_DWELL_MINUTES = "dwell_minutes"             # continuous dwell time
CONF_HYSTERESIS = "hysteresis"                   # anti-flap band (W)

# --- Charging ---
CONF_MAX_CHARGE = "max_charge"                   # max charge power (W)
CONF_SURPLUS_RESERVE = "surplus_reserve"         # keep this much export (W)
CONF_TARGET_SOC = "target_soc"                   # charge goal (%)
CONF_CAPACITY_KWH = "capacity_kwh"               # usable battery capacity (kWh)
CONF_PV_NOMINAL_W = "pv_nominal_w"               # Solarbank PV nominal (W)
CONF_AFTERNOON_HOUR = "afternoon_hour"           # afternoon cap boundary (hour)
CONF_AFTERNOON_FACTOR = "afternoon_factor"       # afternoon cap = nominal * factor

# --- General ---
CONF_INTERVAL = "control_interval"               # coordinator update interval (s)
CONF_DEADBAND = "deadband"                        # min setpoint change to write (W)

# ---------------------------------------------------------------------------
# Defaults (values the operator gave; all overridable in the UI)
# ---------------------------------------------------------------------------
DEFAULT_BATT_DRAW_POSITIVE = True
DEFAULT_GRID_EXPORT_POSITIVE = True
DEFAULT_GRID_FLOW_DISCHARGE = "discharge"
DEFAULT_GRID_FLOW_CHARGE = "charge"

DEFAULT_DISCHARGE_TH1 = 800.0
DEFAULT_DISCHARGE_TH2 = 1600.0
DEFAULT_DISCHARGE_STAGE1 = 350.0
DEFAULT_DISCHARGE_STAGE2 = 800.0
DEFAULT_DWELL_MINUTES = 10.0
DEFAULT_HYSTERESIS = 100.0

DEFAULT_MAX_CHARGE = 2500.0
DEFAULT_SURPLUS_RESERVE = 100.0
DEFAULT_TARGET_SOC = 100.0
DEFAULT_CAPACITY_KWH = 15.5
DEFAULT_PV_NOMINAL_W = 2000.0
DEFAULT_AFTERNOON_HOUR = 13
DEFAULT_AFTERNOON_FACTOR = 1.0 / 3.0

DEFAULT_INTERVAL = 30
DEFAULT_DEADBAND = 25.0

# ---------------------------------------------------------------------------
# Output / diagnostic sensor keys
# ---------------------------------------------------------------------------
KEY_ENABLED = "enabled"
KEY_MODE = "mode"
KEY_TARGET_POWER = "target_power"
KEY_DEMAND = "corrected_demand"
KEY_SURPLUS = "surplus"

# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------
SERVICE_ENABLE = "enable"
SERVICE_DISABLE = "disable"
SERVICE_RECALCULATE_NOW = "recalculate_now"


def build_cfg(options: dict) -> dict:
    """Collect the tunable parameters into the plain dict logic.decide expects."""
    def g(key, default):
        return options.get(key, default)

    return {
        "discharge_steps": [0.0, g(CONF_DISCHARGE_STAGE1, DEFAULT_DISCHARGE_STAGE1),
                            g(CONF_DISCHARGE_STAGE2, DEFAULT_DISCHARGE_STAGE2)],
        "discharge_thresholds": [g(CONF_DISCHARGE_TH1, DEFAULT_DISCHARGE_TH1),
                                 g(CONF_DISCHARGE_TH2, DEFAULT_DISCHARGE_TH2)],
        "hysteresis": g(CONF_HYSTERESIS, DEFAULT_HYSTERESIS),
        "dwell_s": g(CONF_DWELL_MINUTES, DEFAULT_DWELL_MINUTES) * 60.0,
        "max_charge": g(CONF_MAX_CHARGE, DEFAULT_MAX_CHARGE),
        "surplus_reserve": g(CONF_SURPLUS_RESERVE, DEFAULT_SURPLUS_RESERVE),
        "target_soc": g(CONF_TARGET_SOC, DEFAULT_TARGET_SOC),
        "capacity_kwh": g(CONF_CAPACITY_KWH, DEFAULT_CAPACITY_KWH),
        "pv_nominal_w": g(CONF_PV_NOMINAL_W, DEFAULT_PV_NOMINAL_W),
        "afternoon_hour": int(g(CONF_AFTERNOON_HOUR, DEFAULT_AFTERNOON_HOUR)),
        "afternoon_factor": g(CONF_AFTERNOON_FACTOR, DEFAULT_AFTERNOON_FACTOR),
    }
