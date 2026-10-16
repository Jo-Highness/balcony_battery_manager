"""Best-effort suggestions for the initial config flow.

Only pre-fills a field when exactly ONE entity matches (unambiguous), otherwise
the field stays empty. Matching prefers device class / unit over names, and
never guesses sign conventions or the optional main-battery SoC. Everything is
only a suggestion that the user reviews in the form.
"""

from __future__ import annotations

from collections.abc import Callable
import contextlib
from typing import Any

from homeassistant.const import ATTR_DEVICE_CLASS, ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

from . import const as C, units

# Integrations that expose the Solarbank (official + community).
ANKER_PLATFORMS = {"anker_solix_official", "anker_solix"}


def _is_power(st: State) -> bool:
    unit = st.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
    return bool(unit) and units.factor(unit, units.POWER_TO_W) is not None


def _is_percent(st: State) -> bool:
    return st.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == "%" or (
        st.attributes.get(ATTR_DEVICE_CLASS) == "battery"
    )


def _unique(states: list[State]) -> State | None:
    return states[0] if len(states) == 1 else None


def suggest(hass: HomeAssistant) -> dict[str, Any]:
    """Return a dict of CONF_* -> suggested entity_id / value."""
    ent_reg = er.async_get(hass)

    def is_anker(st: State) -> bool:
        entry = ent_reg.async_get(st.entity_id)
        if entry is not None and entry.platform in ANKER_PLATFORMS:
            return True
        return "solarbank" in st.entity_id

    def pick(domain: str, anker: bool, pred: Callable[[State], bool], *tokens: str) -> State | None:
        matches = [
            st
            for st in hass.states.async_all(domain)
            if is_anker(st) is anker
            and pred(st)
            and (not tokens or any(t in st.entity_id for t in tokens))
        ]
        return _unique(matches)

    def any_state(_st: State) -> bool:
        return True

    s: dict[str, Any] = {}

    # --- Solarbank sensors -------------------------------------------------
    if st := pick("sensor", True, _is_percent, "state_of_charge", "_soc"):
        s[C.CONF_SOC_ANKER] = st.entity_id
    if st := pick("sensor", True, _is_power, "solar_power", "pv_power"):
        s[C.CONF_P_ANKER_PV] = st.entity_id
    if st := pick("sensor", True, _is_power, "ac_output", "output_power"):
        s[C.CONF_P_ANKER_OUT] = st.entity_id

    # --- Solarbank actuators ----------------------------------------------
    if st := pick("select", True, any_state, "grid_flow"):
        s[C.CONF_GRID_FLOW_SELECT] = st.entity_id
        options = [str(o) for o in st.attributes.get("options") or []]
        discharge = [o for o in options if "discharge" in o.lower()]
        charge = [o for o in options if "charge" in o.lower() and "discharge" not in o.lower()]
        if len(discharge) == 1:
            s[C.CONF_GRID_FLOW_DISCHARGE] = discharge[0]
        if len(charge) == 1:
            s[C.CONF_GRID_FLOW_CHARGE] = charge[0]
    if st := pick("number", True, any_state, "target_grid_power"):
        s[C.CONF_TARGET_POWER_NUMBER] = st.entity_id

    # --- Usable capacity (Wh / kWh) ---------------------------------------
    if st := pick("sensor", True, any_state, "battery_capacity"):
        with contextlib.suppress(ValueError, TypeError):
            kwh = units.convert(
                float(st.state), st.attributes.get(ATTR_UNIT_OF_MEASUREMENT), units.ENERGY_TO_KWH
            )
            if kwh and kwh > 0:
                s[C.CONF_CAPACITY_KWH] = round(kwh, 2)

    # --- House side (only if exactly one power sensor matches) ------------
    if st := pick("sensor", False, _is_power, "grid"):
        s[C.CONF_P_GRID] = st.entity_id
    if st := pick("sensor", False, _is_power, "battery"):
        s[C.CONF_P_BATT_DRAW] = st.entity_id

    # --- Sun ---------------------------------------------------------------
    if hass.states.get("sun.sun"):
        s[C.CONF_SUN] = "sun.sun"

    return s
