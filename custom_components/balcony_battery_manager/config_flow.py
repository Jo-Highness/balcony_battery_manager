"""Config & options flow for Balcony Battery Manager (v2, Solarbank 4)."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from . import const as C
from . import prefill


def _entity_sel(*domains: str) -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain=list(domains)))


def _num_sel(minimum: float, maximum: float, step: float, unit: str) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum, max=maximum, step=step,
            mode=selector.NumberSelectorMode.BOX, unit_of_measurement=unit))


def _schema(defaults: dict) -> vol.Schema:
    """Full parameter schema; `defaults` supplies suggested_value per key."""

    def d(key, fallback):
        val = defaults.get(key, fallback)
        return {"suggested_value": val} if val is not None else vol.UNDEFINED

    return vol.Schema({
        # --- Inputs ---
        vol.Required(C.CONF_P_BATT_DRAW, description=d(C.CONF_P_BATT_DRAW, None)): _entity_sel("sensor"),
        vol.Required(C.CONF_BATT_DRAW_POSITIVE,
                     default=defaults.get(C.CONF_BATT_DRAW_POSITIVE, C.DEFAULT_BATT_DRAW_POSITIVE)): bool,
        vol.Required(C.CONF_P_ANKER_OUT, description=d(C.CONF_P_ANKER_OUT, None)): _entity_sel("sensor"),
        vol.Required(C.CONF_P_GRID, description=d(C.CONF_P_GRID, None)): _entity_sel("sensor"),
        vol.Required(C.CONF_GRID_EXPORT_POSITIVE,
                     default=defaults.get(C.CONF_GRID_EXPORT_POSITIVE, C.DEFAULT_GRID_EXPORT_POSITIVE)): bool,
        vol.Required(C.CONF_SOC_ANKER, description=d(C.CONF_SOC_ANKER, None)): _entity_sel("sensor"),
        vol.Required(C.CONF_P_ANKER_PV, description=d(C.CONF_P_ANKER_PV, None)): _entity_sel("sensor"),
        vol.Required(C.CONF_SUN, description=d(C.CONF_SUN, "sun.sun")): _entity_sel("sun"),
        # --- Actors ---
        vol.Required(C.CONF_GRID_FLOW_SELECT, description=d(C.CONF_GRID_FLOW_SELECT, None)): _entity_sel("select", "input_select"),
        vol.Required(C.CONF_GRID_FLOW_DISCHARGE,
                     default=defaults.get(C.CONF_GRID_FLOW_DISCHARGE, C.DEFAULT_GRID_FLOW_DISCHARGE)): str,
        vol.Required(C.CONF_GRID_FLOW_CHARGE,
                     default=defaults.get(C.CONF_GRID_FLOW_CHARGE, C.DEFAULT_GRID_FLOW_CHARGE)): str,
        vol.Required(C.CONF_TARGET_POWER_NUMBER, description=d(C.CONF_TARGET_POWER_NUMBER, None)): _entity_sel("number", "input_number"),
        # --- Discharge staircase ---
        vol.Required(C.CONF_DISCHARGE_TH1,
                     default=defaults.get(C.CONF_DISCHARGE_TH1, C.DEFAULT_DISCHARGE_TH1)): _num_sel(0, 10000, 10, "W"),
        vol.Required(C.CONF_DISCHARGE_TH2,
                     default=defaults.get(C.CONF_DISCHARGE_TH2, C.DEFAULT_DISCHARGE_TH2)): _num_sel(0, 10000, 10, "W"),
        vol.Required(C.CONF_DISCHARGE_STAGE1,
                     default=defaults.get(C.CONF_DISCHARGE_STAGE1, C.DEFAULT_DISCHARGE_STAGE1)): _num_sel(0, 5000, 10, "W"),
        vol.Required(C.CONF_DISCHARGE_STAGE2,
                     default=defaults.get(C.CONF_DISCHARGE_STAGE2, C.DEFAULT_DISCHARGE_STAGE2)): _num_sel(0, 5000, 10, "W"),
        vol.Required(C.CONF_DWELL_MINUTES,
                     default=defaults.get(C.CONF_DWELL_MINUTES, C.DEFAULT_DWELL_MINUTES)): _num_sel(0, 120, 0.5, "min"),
        vol.Required(C.CONF_HYSTERESIS,
                     default=defaults.get(C.CONF_HYSTERESIS, C.DEFAULT_HYSTERESIS)): _num_sel(0, 2000, 10, "W"),
        # --- Charging ---
        vol.Required(C.CONF_MAX_CHARGE,
                     default=defaults.get(C.CONF_MAX_CHARGE, C.DEFAULT_MAX_CHARGE)): _num_sel(0, 10000, 50, "W"),
        vol.Required(C.CONF_SURPLUS_RESERVE,
                     default=defaults.get(C.CONF_SURPLUS_RESERVE, C.DEFAULT_SURPLUS_RESERVE)): _num_sel(0, 2000, 10, "W"),
        vol.Required(C.CONF_TARGET_SOC,
                     default=defaults.get(C.CONF_TARGET_SOC, C.DEFAULT_TARGET_SOC)): _num_sel(0, 100, 1, "%"),
        vol.Required(C.CONF_CAPACITY_KWH,
                     default=defaults.get(C.CONF_CAPACITY_KWH, C.DEFAULT_CAPACITY_KWH)): _num_sel(0.1, 100, 0.1, "kWh"),
        vol.Required(C.CONF_PV_NOMINAL_W,
                     default=defaults.get(C.CONF_PV_NOMINAL_W, C.DEFAULT_PV_NOMINAL_W)): _num_sel(0, 20000, 50, "W"),
        vol.Required(C.CONF_AFTERNOON_HOUR,
                     default=defaults.get(C.CONF_AFTERNOON_HOUR, C.DEFAULT_AFTERNOON_HOUR)): _num_sel(0, 23, 1, "h"),
        vol.Required(C.CONF_AFTERNOON_FACTOR,
                     default=defaults.get(C.CONF_AFTERNOON_FACTOR, C.DEFAULT_AFTERNOON_FACTOR)): _num_sel(0, 1, 0.01, ""),
        # --- General ---
        vol.Required(C.CONF_INTERVAL,
                     default=defaults.get(C.CONF_INTERVAL, C.DEFAULT_INTERVAL)): _num_sel(5, 600, 5, "s"),
        vol.Required(C.CONF_DEADBAND,
                     default=defaults.get(C.CONF_DEADBAND, C.DEFAULT_DEADBAND)): _num_sel(0, 500, 5, "W"),
    })


class BalconyBatteryConfigFlow(ConfigFlow, domain=C.DOMAIN):
    """Initial setup."""

    VERSION = C.CONFIG_VERSION

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="Balcony Battery Manager", data=user_input)
        defaults = prefill.suggest(self.hass)
        return self.async_show_form(step_id="user", data_schema=_schema(defaults))

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> "BalconyBatteryOptionsFlow":
        return BalconyBatteryOptionsFlow(entry)


class BalconyBatteryOptionsFlow(OptionsFlow):
    """Edit every parameter later via the UI."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        # current values (options override data) become the suggested defaults
        current = {**self._entry.data, **self._entry.options}
        return self.async_show_form(step_id="init", data_schema=_schema(current))
