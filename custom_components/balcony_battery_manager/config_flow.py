"""Config & options flow for Balcony Battery Manager (v2, Solarbank 4).

The ~35 parameters are grouped into collapsible sections. All settings are
stored flat in ``entry.options`` (``entry.data`` stays empty), so the options
flow can clear optional fields simply by leaving them empty.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector
import voluptuous as vol

from . import const as C, prefill, units

TITLE = "Balcony Battery Manager"

SEC_MEASUREMENTS = "measurements"
SEC_ACTUATORS = "actuators"
SEC_DISCHARGE = "discharge"
SEC_CHARGING = "charging"
SEC_GRID_SUPPORT = "grid_support"
SEC_GENERAL = "general"

# section -> collapsed by default
SECTIONS: dict[str, bool] = {
    SEC_MEASUREMENTS: False,
    SEC_ACTUATORS: False,
    SEC_DISCHARGE: True,
    SEC_CHARGING: True,
    SEC_GRID_SUPPORT: True,
    SEC_GENERAL: True,
}

_POWER_SENSORS = (C.CONF_P_BATT_DRAW, C.CONF_P_ANKER_OUT, C.CONF_P_GRID, C.CONF_P_ANKER_PV)
_SOC_SENSORS = (C.CONF_SOC_ANKER, C.CONF_MAIN_SOC)


def _entity_sel(*domains: str) -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=list(domains)))


def _num_sel(minimum: float, maximum: float, step: float, unit: str) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=step,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement=unit,
        )
    )


_TEXT = selector.TextSelector()


def _section_schemas(defaults: dict[str, Any]) -> dict[str, dict]:
    """Field schema per section; ``defaults`` supplies the current/suggested values."""

    def sug(key: str, fallback: Any = None) -> dict | None:
        # Return None (no description) when there is no suggestion: a
        # vol.UNDEFINED description makes the form un-serialisable (HTTP 500).
        val = defaults.get(key, fallback)
        return {"suggested_value": val} if val is not None else None

    def req(key: str, default: Any) -> vol.Required:
        return vol.Required(key, default=defaults.get(key, default))

    return {
        SEC_MEASUREMENTS: {
            vol.Required(C.CONF_P_BATT_DRAW, description=sug(C.CONF_P_BATT_DRAW)): _entity_sel(
                "sensor"
            ),
            req(C.CONF_BATT_DRAW_POSITIVE, C.DEFAULT_BATT_DRAW_POSITIVE): bool,
            vol.Required(C.CONF_P_GRID, description=sug(C.CONF_P_GRID)): _entity_sel("sensor"),
            req(C.CONF_GRID_EXPORT_POSITIVE, C.DEFAULT_GRID_EXPORT_POSITIVE): bool,
            vol.Required(C.CONF_P_ANKER_OUT, description=sug(C.CONF_P_ANKER_OUT)): _entity_sel(
                "sensor"
            ),
            vol.Required(C.CONF_SOC_ANKER, description=sug(C.CONF_SOC_ANKER)): _entity_sel(
                "sensor"
            ),
            vol.Required(C.CONF_P_ANKER_PV, description=sug(C.CONF_P_ANKER_PV)): _entity_sel(
                "sensor"
            ),
            vol.Optional(C.CONF_SUN, description=sug(C.CONF_SUN)): _entity_sel("sun"),
        },
        SEC_ACTUATORS: {
            vol.Required(
                C.CONF_GRID_FLOW_SELECT, description=sug(C.CONF_GRID_FLOW_SELECT)
            ): _entity_sel("select", "input_select"),
            req(C.CONF_GRID_FLOW_DISCHARGE, C.DEFAULT_GRID_FLOW_DISCHARGE): _TEXT,
            req(C.CONF_GRID_FLOW_CHARGE, C.DEFAULT_GRID_FLOW_CHARGE): _TEXT,
            vol.Required(
                C.CONF_TARGET_POWER_NUMBER, description=sug(C.CONF_TARGET_POWER_NUMBER)
            ): _entity_sel("number", "input_number"),
            vol.Optional(C.CONF_MODE_SELECT, description=sug(C.CONF_MODE_SELECT)): _entity_sel(
                "select", "input_select"
            ),
            vol.Optional(C.CONF_CONTROL_MODE, description=sug(C.CONF_CONTROL_MODE)): _TEXT,
            vol.Optional(C.CONF_RESTORE_MODE, description=sug(C.CONF_RESTORE_MODE)): _TEXT,
        },
        SEC_DISCHARGE: {
            req(C.CONF_DISCHARGE_TH1, C.DEFAULT_DISCHARGE_TH1): _num_sel(0, 10000, 10, "W"),
            req(C.CONF_DISCHARGE_TH2, C.DEFAULT_DISCHARGE_TH2): _num_sel(0, 10000, 10, "W"),
            req(C.CONF_DISCHARGE_STAGE1, C.DEFAULT_DISCHARGE_STAGE1): _num_sel(0, 5000, 10, "W"),
            req(C.CONF_DISCHARGE_STAGE2, C.DEFAULT_DISCHARGE_STAGE2): _num_sel(0, 5000, 10, "W"),
            req(C.CONF_DWELL_MINUTES, C.DEFAULT_DWELL_MINUTES): _num_sel(0, 120, 0.5, "min"),
            req(C.CONF_HYSTERESIS, C.DEFAULT_HYSTERESIS): _num_sel(0, 2000, 10, "W"),
            req(C.CONF_MIN_DISCHARGE_SOC, C.DEFAULT_MIN_DISCHARGE_SOC): _num_sel(0, 100, 1, "%"),
        },
        SEC_CHARGING: {
            req(C.CONF_MAX_CHARGE, C.DEFAULT_MAX_CHARGE): _num_sel(0, 10000, 50, "W"),
            req(C.CONF_SURPLUS_RESERVE, C.DEFAULT_SURPLUS_RESERVE): _num_sel(0, 2000, 10, "W"),
            req(C.CONF_TARGET_SOC, C.DEFAULT_TARGET_SOC): _num_sel(0, 100, 1, "%"),
            req(C.CONF_CAPACITY_KWH, C.DEFAULT_CAPACITY_KWH): _num_sel(0.1, 100, 0.1, "kWh"),
            req(C.CONF_PV_NOMINAL_W, C.DEFAULT_PV_NOMINAL_W): _num_sel(0, 20000, 50, "W"),
            req(C.CONF_AFTERNOON_HOUR, C.DEFAULT_AFTERNOON_HOUR): _num_sel(0, 23, 1, "h"),
            req(C.CONF_AFTERNOON_FACTOR, C.DEFAULT_AFTERNOON_FACTOR): _num_sel(0, 1, 0.01, ""),
        },
        SEC_GRID_SUPPORT: {
            req(C.CONF_GRID_SUPPORT_ENABLED, C.DEFAULT_GRID_SUPPORT_ENABLED): bool,
            vol.Optional(C.CONF_MAIN_SOC, description=sug(C.CONF_MAIN_SOC)): _entity_sel("sensor"),
            req(C.CONF_MAIN_EMPTY_SOC, C.DEFAULT_MAIN_EMPTY_SOC): _num_sel(0, 100, 1, "%"),
            req(C.CONF_MAIN_EMPTY_SOC_HYST, C.DEFAULT_MAIN_EMPTY_SOC_HYST): _num_sel(0, 50, 1, "%"),
            req(C.CONF_GRID_SUPPORT_MARGIN, C.DEFAULT_GRID_SUPPORT_MARGIN): _num_sel(
                0, 2000, 10, "W"
            ),
            req(C.CONF_GRID_SUPPORT_MAX, C.DEFAULT_GRID_SUPPORT_MAX): _num_sel(0, 10000, 50, "W"),
        },
        SEC_GENERAL: {
            req(C.CONF_INTERVAL, C.DEFAULT_INTERVAL): _num_sel(5, 600, 5, "s"),
            req(C.CONF_DEADBAND, C.DEFAULT_DEADBAND): _num_sel(0, 500, 5, "W"),
        },
    }


def build_schema(defaults: dict[str, Any]) -> vol.Schema:
    """The sectioned form schema."""
    schemas = _section_schemas(defaults)
    return vol.Schema(
        {
            vol.Required(name): section(vol.Schema(schemas[name]), {"collapsed": collapsed})
            for name, collapsed in SECTIONS.items()
        }
    )


def flatten(user_input: dict[str, Any]) -> dict[str, Any]:
    """Sectioned form input -> flat option dict (empty optional values dropped)."""
    flat: dict[str, Any] = {}
    for key, value in user_input.items():
        if isinstance(value, dict):
            flat.update(value)
        else:
            flat[key] = value
    return {k: v for k, v in flat.items() if v not in (None, "")}


def _unit(hass: HomeAssistant, eid: str | None) -> tuple[bool, Any]:
    """(state exists, unit) of an entity."""
    st = hass.states.get(eid) if eid else None
    return st is not None, (st.attributes.get(ATTR_UNIT_OF_MEASUREMENT) if st else None)


def _options_of(hass: HomeAssistant, eid: str | None) -> list[str] | None:
    st = hass.states.get(eid) if eid else None
    opts = st.attributes.get("options") if st else None
    return list(opts) if isinstance(opts, (list, tuple)) else None


def validate(
    hass: HomeAssistant, flat: dict[str, Any], *, exclude_entry_id: str | None = None
) -> str | None:
    """Return an error key for an invalid configuration, else None."""
    if flat[C.CONF_DISCHARGE_TH1] >= flat[C.CONF_DISCHARGE_TH2]:
        return "threshold_order"
    if flat[C.CONF_DISCHARGE_STAGE1] > flat[C.CONF_DISCHARGE_STAGE2]:
        return "stage_order"

    discharge = flat[C.CONF_GRID_FLOW_DISCHARGE]
    charge = flat[C.CONF_GRID_FLOW_CHARGE]
    if discharge == charge:
        return "grid_flow_options_equal"
    options = _options_of(hass, flat[C.CONF_GRID_FLOW_SELECT])
    if options is not None and (discharge not in options or charge not in options):
        return "grid_flow_option_missing"

    mode_select = flat.get(C.CONF_MODE_SELECT)
    control = flat.get(C.CONF_CONTROL_MODE)
    restore = flat.get(C.CONF_RESTORE_MODE)
    if (control or restore) and not mode_select:
        return "mode_select_missing"
    if mode_select:
        if not (control or restore):
            return "mode_option_required"
        options = _options_of(hass, mode_select)
        if options is not None and any(o and o not in options for o in (control, restore)):
            return "mode_option_missing"

    for key in _POWER_SENSORS:
        exists, unit = _unit(hass, flat.get(key))
        if exists and units.factor(unit, units.POWER_TO_W) is None:
            return "power_unit_invalid"
    for key in _SOC_SENSORS:
        exists, unit = _unit(hass, flat.get(key))
        if exists and units.factor(unit, units.PERCENT) is None:
            return "soc_unit_invalid"
    exists, unit = _unit(hass, flat[C.CONF_TARGET_POWER_NUMBER])
    if exists and units.factor(unit, units.POWER_TO_W) is None:
        return "number_unit_invalid"

    for entry in hass.config_entries.async_entries(C.DOMAIN):
        if entry.entry_id == exclude_entry_id:
            continue
        other = {**entry.data, **entry.options}
        for key in (C.CONF_TARGET_POWER_NUMBER, C.CONF_GRID_FLOW_SELECT):
            if flat.get(key) and other.get(key) == flat.get(key):
                return "actuator_in_use"
    return None


class BalconyBatteryConfigFlow(ConfigFlow, domain=C.DOMAIN):
    """Initial setup."""

    VERSION = C.CONFIG_VERSION
    MINOR_VERSION = C.CONFIG_MINOR_VERSION

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            flat = flatten(user_input)
            if error := validate(self.hass, flat):
                if error == "actuator_in_use":
                    return self.async_abort(reason="already_configured")
                errors["base"] = error
            else:
                await self.async_set_unique_id(flat[C.CONF_TARGET_POWER_NUMBER])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=TITLE, data={}, options=flat)
            defaults = flat
        else:
            defaults = prefill.suggest(self.hass)
        return self.async_show_form(
            step_id="user", data_schema=build_schema(defaults), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> BalconyBatteryOptionsFlow:
        return BalconyBatteryOptionsFlow()


class BalconyBatteryOptionsFlow(OptionsFlow):
    """Edit every parameter later via the UI."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self.config_entry
        errors: dict[str, str] = {}
        if user_input is not None:
            # Build the new options from the form only (no merge onto the old
            # values) so cleared optional fields are really removed.
            flat = flatten(user_input)
            if error := validate(self.hass, flat, exclude_entry_id=entry.entry_id):
                errors["base"] = error
            else:
                number = flat[C.CONF_TARGET_POWER_NUMBER]
                if entry.unique_id != number:
                    self.hass.config_entries.async_update_entry(entry, unique_id=number)
                return self.async_create_entry(title="", data=flat)
            current = flat
        else:
            current = {**entry.data, **entry.options}
        return self.async_show_form(
            step_id="init", data_schema=build_schema(current), errors=errors
        )
