"""Best-effort auto-detection of entity defaults for the initial config flow.

Only used to pre-fill suggested values; the user can always override. Matches
the Anker SOLIX (official integration, Solarbank 4) actor/sensor entities and
the house-side E3DC/KNX meters by entity-id pattern.
"""
from __future__ import annotations

from homeassistant.core import HomeAssistant

from . import const as C


def _find(hass: HomeAssistant, *needles: str, domain: str | None = None,
          platform_hint: str | None = None) -> str | None:
    """First entity whose id contains all needles (and matches domain)."""
    for state in hass.states.async_all():
        eid = state.entity_id
        if domain and not eid.startswith(domain + "."):
            continue
        low = eid.lower()
        if all(n in low for n in needles):
            return eid
    return None


def suggest(hass: HomeAssistant) -> dict:
    """Return a dict of CONF_* -> suggested entity_id / value."""
    s: dict = {}
    sb = "solarbank_4"  # official Solarbank-4 entity id fragment

    # --- Solarbank (Solix 4) sensors ---
    s[C.CONF_P_ANKER_OUT] = _find(hass, sb, "ac_output", domain="sensor")
    s[C.CONF_SOC_ANKER] = _find(hass, sb, "soc", domain="sensor")
    s[C.CONF_P_ANKER_PV] = _find(hass, sb, "solar_power", domain="sensor")

    # --- Solarbank actors ---
    s[C.CONF_GRID_FLOW_SELECT] = _find(hass, sb, "grid_flow", domain="select")
    s[C.CONF_TARGET_POWER_NUMBER] = _find(hass, sb, "target_grid_power", domain="number")

    # --- House side (E3DC via KNX) ---
    s[C.CONF_P_BATT_DRAW] = _find(hass, "batterypowerconsumption", domain="sensor")
    s[C.CONF_P_GRID] = _find(hass, "gridpowerconsumption", domain="sensor")

    # --- Sun ---
    s[C.CONF_SUN] = "sun.sun" if hass.states.get("sun.sun") else None

    # --- Capacity from the Solarbank battery_capacity sensor value ---
    cap_eid = _find(hass, sb, "battery_capacity", domain="sensor")
    if cap_eid:
        st = hass.states.get(cap_eid)
        try:
            s[C.CONF_CAPACITY_KWH] = round(float(st.state), 2)
        except (ValueError, TypeError, AttributeError):
            pass

    return {k: v for k, v in s.items() if v is not None}
