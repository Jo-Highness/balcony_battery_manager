"""Best-effort config-flow pre-fill helpers.

Two pure look-ups produce ``{CONF_*: entity_id}`` suggestions for the initial
config flow:

* :func:`suggested_inputs_from_energy` resolves the grid / main-battery power &
  SoC sensors from the Home Assistant **Energy Dashboard**. The dashboard stores
  *energy* statistics (kWh), so we never copy those into a power field — instead
  we walk energy-entity -> device -> sibling *power* / *battery* entity.
* :func:`suggested_from_anker` resolves the balcony-battery inputs and the Anker
  control entities from a single ``anker_solix`` Solarbank device.

Both functions are deliberately conservative: a suggestion is only emitted when
exactly **one** candidate matches, otherwise the field is left empty. Matching
prefers the registry ``translation_key`` / ``unique_id`` suffix over localized
display names (which change with the UI language). Nothing here ever raises;
every failure path simply yields fewer suggestions, and the caller only ever
uses the result as ``suggested_value``.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import (
    CONF_AC_CHARGE_NUMBER,
    CONF_AC_CHARGE_SWITCH,
    CONF_BALCONY_POWER,
    CONF_BALCONY_SOC,
    CONF_DISCHARGE_NUMBER,
    CONF_GRID_POWER,
    CONF_MAIN_POWER,
    CONF_MAIN_SOC,
    CONF_MODE_SELECT,
)

_LOGGER = logging.getLogger(__name__)

ANKER_DOMAIN = "anker_solix"

_POWER_UNITS = {"w", "kw"}

# --- anker_solix translation_key / unique_id suffix allowlists ---------------
# Matching is "exactly one candidate or nothing", and the two W-number sets are
# disjoint, so a wrong assignment is structurally impossible: a number that
# cannot be told apart simply yields no suggestion. The Anker control entities
# are disabled by default in the integration, so these may not match until the
# user enables them — that is fine, the field just stays empty.
_SOC_SUFFIXES = ("state_of_charge", "soc")
_BATTERY_POWER_SUFFIXES = ("battery_power",)
_USAGE_MODE_SUFFIXES = ("usage_mode",)
_AC_SOCKET_SUFFIXES = ("ac_socket", "ac_output", "output_switch")
# System / home output preset (the discharge / home-load number).
_SYSTEM_OUTPUT_SUFFIXES = (
    "system_output_power",
    "output_power",
    "home_load_preset",
    "home_preset",
    "output_preset",
    "preset_output_power",
)
# AC charge / AC input limit (the AC-charge number).
_AC_INPUT_SUFFIXES = (
    "ac_input_limit",
    "ac_input_power",
    "ac_charge_power",
    "ac_charge_limit",
    "charge_power_limit",
)


# --- small registry helpers --------------------------------------------------
def _device_class(hass: HomeAssistant, ent: er.RegistryEntry) -> str | None:
    """Device class from the registry, falling back to the live state."""
    dc = ent.device_class or ent.original_device_class
    if dc:
        return dc
    state = hass.states.get(ent.entity_id)
    if state:
        return state.attributes.get("device_class")
    return None


def _unit(hass: HomeAssistant, ent: er.RegistryEntry) -> str | None:
    """Unit of measurement from the registry, falling back to the live state."""
    unit = getattr(ent, "unit_of_measurement", None)
    if unit:
        return unit
    state = hass.states.get(ent.entity_id)
    if state:
        return state.attributes.get("unit_of_measurement")
    return None


def _matches_suffix(ent: er.RegistryEntry, suffixes: tuple[str, ...]) -> bool:
    """True if the entity's translation_key / unique_id ends with a suffix."""
    tk = (ent.translation_key or "").lower()
    uid = str(ent.unique_id or "").lower()
    return any(
        tk == s or tk.endswith(s) or uid.endswith(s) or s in uid for s in suffixes
    )


def _pick(
    entities: list[er.RegistryEntry], suffixes: tuple[str, ...]
) -> str | None:
    """Return the single best candidate's entity_id, or None if ambiguous.

    If there is exactly one candidate it is used directly; otherwise the list is
    narrowed by suffix and only a unique remaining match is returned.
    """
    if len(entities) == 1:
        return entities[0].entity_id
    narrowed = [e for e in entities if _matches_suffix(e, suffixes)]
    return narrowed[0].entity_id if len(narrowed) == 1 else None


def _device_id_for_stat(
    ent_reg: er.EntityRegistry, stat_entity_id: str | None
) -> str | None:
    if not stat_entity_id:
        return None
    entry = ent_reg.async_get(stat_entity_id)
    return entry.device_id if entry else None


def _power_sensor_for_device(
    hass: HomeAssistant, ent_reg: er.EntityRegistry, device_id: str
) -> str | None:
    """The single power sensor on a device (device_class power or W/kW unit)."""
    candidates: list[str] = []
    for ent in er.async_entries_for_device(
        ent_reg, device_id, include_disabled_entities=True
    ):
        if ent.domain != "sensor":
            continue
        unit = _unit(hass, ent)
        if _device_class(hass, ent) == "power" or (
            unit and unit.strip().lower() in _POWER_UNITS
        ):
            candidates.append(ent.entity_id)
    return candidates[0] if len(candidates) == 1 else None


def _soc_sensor_for_device(
    hass: HomeAssistant, ent_reg: er.EntityRegistry, device_id: str
) -> str | None:
    """The single battery-SoC sensor on a device (device_class battery, %)."""
    candidates: list[str] = []
    for ent in er.async_entries_for_device(
        ent_reg, device_id, include_disabled_entities=True
    ):
        if ent.domain != "sensor":
            continue
        if _device_class(hass, ent) == "battery" and _unit(hass, ent) == "%":
            candidates.append(ent.entity_id)
    return candidates[0] if len(candidates) == 1 else None


def _first_grid_stat(source: dict[str, Any]) -> str | None:
    """Pick any energy statistic that identifies the grid device.

    Real HA stores grid flows as ``flow_from[]`` / ``flow_to[]`` lists; some
    representations flatten them onto the source. Both shapes are handled.
    """
    for key in ("flow_from", "flow_to"):
        for flow in source.get(key) or []:
            stat = flow.get("stat_energy_from") or flow.get("stat_energy_to")
            if stat:
                return stat
    return source.get("stat_energy_from") or source.get("stat_energy_to")


# --- public resolvers --------------------------------------------------------
async def suggested_inputs_from_energy(hass: HomeAssistant) -> dict[str, str]:
    """Best-effort grid / main-battery suggestions from the Energy Dashboard."""
    out: dict[str, str] = {}
    try:
        from homeassistant.components.energy.data import async_get_manager

        manager = await async_get_manager(hass)
    except Exception as err:  # noqa: BLE001 - energy may be unconfigured
        _LOGGER.debug("Energy manager unavailable for pre-fill: %s", err)
        return out

    data = getattr(manager, "data", None) or {}
    sources = data.get("energy_sources", [])
    ent_reg = er.async_get(hass)

    for source in sources:
        stype = source.get("type")
        if stype == "grid":
            device_id = _device_id_for_stat(ent_reg, _first_grid_stat(source))
            if device_id:
                power = _power_sensor_for_device(hass, ent_reg, device_id)
                if power:
                    out.setdefault(CONF_GRID_POWER, power)
        elif stype == "battery":
            stat = source.get("stat_energy_from") or source.get("stat_energy_to")
            device_id = _device_id_for_stat(ent_reg, stat)
            if device_id:
                power = _power_sensor_for_device(hass, ent_reg, device_id)
                if power:
                    out.setdefault(CONF_MAIN_POWER, power)
                soc = _soc_sensor_for_device(hass, ent_reg, device_id)
                if soc:
                    out.setdefault(CONF_MAIN_SOC, soc)
    return out


def _anker_solarbank_device(hass: HomeAssistant) -> str | None:
    """The single anker_solix Solarbank device, or None if not unambiguous.

    The integration creates several devices (a virtual system device, the
    Solarbank, possibly an inverter). We prefer the device that carries a
    battery-SoC sensor; if that is unique we use it, else if there is exactly
    one anker_solix device at all we fall back to that.
    """
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    anker = [
        device
        for device in dev_reg.devices.values()
        if any(ident[0] == ANKER_DOMAIN for ident in device.identifiers)
    ]
    if not anker:
        return None

    solarbanks = [
        device
        for device in anker
        if _soc_sensor_for_device(hass, ent_reg, device.id) is not None
    ]
    if len(solarbanks) == 1:
        return solarbanks[0].id
    if len(anker) == 1:
        return anker[0].id
    return None


async def suggested_from_anker(hass: HomeAssistant) -> dict[str, str]:
    """Best-effort balcony / Anker-control suggestions from anker_solix."""
    out: dict[str, str] = {}
    device_id = _anker_solarbank_device(hass)
    if not device_id:
        return out

    ent_reg = er.async_get(hass)
    entities = er.async_entries_for_device(
        ent_reg, device_id, include_disabled_entities=True
    )

    sensors = [e for e in entities if e.domain == "sensor"]
    selects = [e for e in entities if e.domain == "select"]
    switches = [e for e in entities if e.domain == "switch"]
    numbers = [e for e in entities if e.domain == "number"]

    # Balcony SoC: a battery-% sensor.
    soc = [
        e
        for e in sensors
        if _device_class(hass, e) == "battery" and _unit(hass, e) == "%"
    ]
    if (val := _pick(soc, _SOC_SUFFIXES)) is not None:
        out[CONF_BALCONY_SOC] = val

    # Balcony power: a power sensor; narrow to the "battery power" one.
    power = [
        e
        for e in sensors
        if _device_class(hass, e) == "power"
        or ((u := _unit(hass, e)) and u.strip().lower() in _POWER_UNITS)
    ]
    narrowed_power = [e for e in power if _matches_suffix(e, _BATTERY_POWER_SUFFIXES)]
    if len(narrowed_power) == 1:
        out[CONF_BALCONY_POWER] = narrowed_power[0].entity_id
    elif len(power) == 1:
        out[CONF_BALCONY_POWER] = power[0].entity_id

    # Usage-mode select.
    if (val := _pick(selects, _USAGE_MODE_SUFFIXES)) is not None:
        out[CONF_MODE_SELECT] = val

    # AC-socket switch.
    if (val := _pick(switches, _AC_SOCKET_SUFFIXES)) is not None:
        out[CONF_AC_CHARGE_SWITCH] = val

    # The two W-number controls. Disjoint suffix sets + unique-candidate rule
    # make a wrong mapping impossible; an entity matching both is dropped.
    w_numbers = [
        e for e in numbers if (u := _unit(hass, e)) and u.strip().lower() == "w"
    ]
    system_out = [e for e in w_numbers if _matches_suffix(e, _SYSTEM_OUTPUT_SUFFIXES)]
    ac_input = [e for e in w_numbers if _matches_suffix(e, _AC_INPUT_SUFFIXES)]
    ambiguous = {e.entity_id for e in system_out} & {e.entity_id for e in ac_input}
    system_out = [e for e in system_out if e.entity_id not in ambiguous]
    ac_input = [e for e in ac_input if e.entity_id not in ambiguous]
    if len(system_out) == 1:
        out[CONF_DISCHARGE_NUMBER] = system_out[0].entity_id
    if len(ac_input) == 1:
        out[CONF_AC_CHARGE_NUMBER] = ac_input[0].entity_id

    return out
