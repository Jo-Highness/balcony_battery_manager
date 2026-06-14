"""Constants for the Balcony Battery Manager integration."""

from __future__ import annotations

DOMAIN = "balcony_battery_manager"

# ---------------------------------------------------------------------------
# Config / Options keys
# ---------------------------------------------------------------------------
# --- Input measurements ---
CONF_GRID_POWER = "grid_power"
CONF_GRID_EXPORT_POSITIVE = "grid_export_positive"
CONF_MAIN_SOC = "main_soc"
CONF_MAIN_POWER = "main_power"
CONF_MAIN_DISCHARGE_POSITIVE = "main_discharge_positive"
CONF_BALCONY_SOC = "balcony_soc"
CONF_BALCONY_POWER = "balcony_power"
CONF_BALCONY_DISCHARGE_POSITIVE = "balcony_discharge_positive"

# --- Power-sensor unit handling (auto | W | kW) ---
CONF_GRID_POWER_UNIT = "grid_power_unit"
CONF_MAIN_POWER_UNIT = "main_power_unit"
CONF_BALCONY_POWER_UNIT = "balcony_power_unit"

# --- Limits / parameters ---
CONF_MAX_CHARGE_POWER = "max_charge_power"
CONF_MAX_HOUSE_FEED = "max_house_feed"
CONF_INTERVAL = "control_interval"
CONF_CHARGE_HEADROOM = "charge_headroom"
CONF_DISCHARGE_ON_THRESHOLD = "discharge_on_threshold"
CONF_DISCHARGE_OFF_THRESHOLD = "discharge_off_threshold"
CONF_DISCHARGE_SHARE = "discharge_share"
CONF_DEADBAND = "deadband"
CONF_FAILSAFE_AFTER = "failsafe_after"

# --- Grid-support (main battery empty -> cover grid import) ---
CONF_GRID_SUPPORT_ENABLED = "grid_support_enabled"
CONF_MAIN_EMPTY_SOC = "main_empty_soc"
CONF_GRID_IMPORT_ON_THRESHOLD = "grid_import_on_threshold"
CONF_GRID_IMPORT_OFF_THRESHOLD = "grid_import_off_threshold"

# --- Balcony control-entity mapping ---
CONF_MODE_SELECT = "mode_select"
CONF_MODE_MANUAL_VALUE = "mode_manual_value"
CONF_DISCHARGE_NUMBER = "discharge_number"
CONF_AC_CHARGE_SWITCH = "ac_charge_switch"
CONF_AC_CHARGE_NUMBER = "ac_charge_number"
CONF_DEACTIVATION_BEHAVIOR = "deactivation_behavior"
CONF_DEACTIVATION_MODE_VALUE = "deactivation_mode_value"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_GRID_EXPORT_POSITIVE = True
DEFAULT_MAIN_DISCHARGE_POSITIVE = True
DEFAULT_BALCONY_DISCHARGE_POSITIVE = True

# Power-unit override; "auto" keeps the existing behaviour (sensor unit is
# auto-detected, unknown units are treated as W) so existing entries need no
# migration.
DEFAULT_POWER_UNIT = "auto"
POWER_UNIT_OPTIONS = ["auto", "W", "kW"]

DEFAULT_MAX_CHARGE_POWER = 1100
DEFAULT_MAX_HOUSE_FEED = 800
DEFAULT_INTERVAL = 300
DEFAULT_CHARGE_HEADROOM = 200
DEFAULT_DISCHARGE_ON_THRESHOLD = 400
DEFAULT_DISCHARGE_OFF_THRESHOLD = 100
DEFAULT_DISCHARGE_SHARE = 50  # percent
DEFAULT_DEADBAND = 25
DEFAULT_FAILSAFE_AFTER = 0  # seconds; 0 = disabled (hold last safe state forever)

DEFAULT_GRID_SUPPORT_ENABLED = True
DEFAULT_MAIN_EMPTY_SOC = 10  # %; main battery considered "empty" at/below this SOC
DEFAULT_GRID_IMPORT_ON_THRESHOLD = 50  # W grid import above which to activate support
DEFAULT_GRID_IMPORT_OFF_THRESHOLD = 20  # W grid import below which to stop (hysteresis)

# Deactivation behaviour options
DEACT_ALL_ZERO = "all_zero"
DEACT_RESTORE = "restore_anker"
DEFAULT_DEACTIVATION_BEHAVIOR = DEACT_ALL_ZERO

# ---------------------------------------------------------------------------
# Operating modes (state machine)
# ---------------------------------------------------------------------------
MODE_IDLE = "idle"
MODE_CHARGING = "charging"
MODE_DISCHARGING = "discharging"
MODE_DISABLED = "disabled"
MODE_OPTIONS = [MODE_IDLE, MODE_CHARGING, MODE_DISCHARGING, MODE_DISABLED]

# Why we are discharging (transparency only; surfaced as a sensor attribute).
REASON_NONE = "none"
REASON_RELIEF = "relief"  # sharing the main battery's discharge load
REASON_GRID_SUPPORT = "grid_support"  # main empty, covering grid import
REASON_BOTH = "both"

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = f"{DOMAIN}."

# States that must never be parsed as numeric input.
IGNORED_STATES = {"unavailable", "unknown", "none", ""}

# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------
SERVICE_ENABLE = "enable"
SERVICE_DISABLE = "disable"
SERVICE_RECALCULATE_NOW = "recalculate_now"

# ---------------------------------------------------------------------------
# Entity keys
# ---------------------------------------------------------------------------
KEY_ENABLED = "enabled"
KEY_MODE = "mode"
KEY_TARGET_CHARGE = "target_charge"
KEY_TARGET_DISCHARGE = "target_discharge"
KEY_SURPLUS = "computed_surplus"

# Attribute keys
ATTR_GRID_POWER = "grid_power_w"
ATTR_MAIN_DISCHARGE = "main_battery_discharge_w"
ATTR_MAIN_SOC = "main_battery_soc"
ATTR_BALCONY_SOC = "balcony_battery_soc"
ATTR_LAST_SENT_CHARGE = "last_sent_charge_w"
ATTR_LAST_SENT_DISCHARGE = "last_sent_discharge_w"
ATTR_LAST_COMMAND = "last_command"
ATTR_LAST_GOOD_DATA = "last_good_data"
ATTR_DATA_VALID = "input_data_valid"
ATTR_THRESHOLDS = "thresholds"
ATTR_DISCHARGE_REASON = "discharge_reason"
