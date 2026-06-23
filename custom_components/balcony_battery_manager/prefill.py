"""Best-effort config-flow pre-fill helpers.

Three pure look-ups produce ``{CONF_*: value}`` suggestions for the initial
config flow. Values are entity_ids for the sensor/control fields, and bool /
str for the sign and manual-mode fields:

* :func:`suggested_inputs_from_energy` resolves grid / main-battery power & SoC
  sensors from the Home Assistant **Energy Dashboard** (energy-entity -> device
  -> sibling power/battery entity).
* :func:`suggested_from_e3dc` is a **vendor pattern** fallback for the roof /
  main system when it is *not* exposed as a HA device or energy source — most
  notably **E3DC**, which here is integrated via KNX group addresses
  (``platform == "knx"``, ``device_id is None``) and therefore never appears in
  the energy dashboard or as a walkable device. It matches by entity_id pattern
  and also emits the correct sign convention.
* :func:`suggested_from_anker` resolves the balcony-battery inputs and the Anker
  control entities from the ``anker_solix`` Solarbank.

All resolvers are deliberately conservative: a suggestion is only emitted when a
candidate is unambiguous (a single match, or a uniquely preferred one). Matching
prefers the registry ``translation_key`` / ``unique_id`` suffix over localized
display names. Nothing here ever raises; every failure path simply yields fewer
suggestions, and the caller only ever uses the result as ``suggested_value``.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import (
    CONF_AC_CHARGE_NUMBER,
    CONF_AC_CHARGE_SWITCH,
    CONF_BALCONY_DISCHARGE_POSITIVE,
    CONF_BALCONY_POWER,
    CONF_BALCONY_SOC,
    CONF_DISCHARGE_NUMBER,
    CONF_GRID_EXPORT_POSITIVE,
    CONF_GRID_POWER,
    CONF_MAIN_DISCHARGE_POSITIVE,
    CONF_MAIN_POWER,
    CONF_MAIN_SOC,
    CONF_MODE_MANUAL_VALUE,
    CONF_MODE_SELECT,
)

_LOGGER = logging.getLogger(__name__)

ANKER_DOMAIN = "anker_solix"

_POWER_UNITS = {"w", "kw"}

# --- anker_solix translation_key / unique_id suffix allowlists ---------------
# Matching is "unambiguous or nothing", so a wrong assignment is structurally
# impossible: a candidate that cannot be told apart simply yields no suggestion.
# Several Anker control entities are disabled by default in the integration, so
# these may not match until the user enables them — that is fine, the field just
# stays empty.
#
# SoC is matched by *ordered* preference because a Solarbank exposes several
# battery-% sensors (whole-system ``state_of_charge``, ``main_battery_soc`` and
# one ``exp_N_soc`` per expansion pack); we want the whole-system value and must
# not pick an expansion pack.
_SOC_PREFERENCE = ("state_of_charge", "main_battery_soc")
_BATTERY_POWER_SUFFIXES = ("battery_power",)
_USAGE_MODE_SUFFIXES = ("usage_mode",)
# AC-charge *enable* switch (the MQTT `ac_charge` switch that actually triggers
# grid charging) — deliberately NOT `ac_socket`, which is the AC *output* socket.
_AC_CHARGE_SWITCH_SUFFIXES = ("ac_charge_switch", "ac_charge")
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

# --- E3DC (roof system) entity_id patterns -----------------------------------
# E3DC's RSCP/KNX power values follow the "consumption" sign convention:
#   grid:    positive == drawing FROM the grid (import), negative == export
#   battery: positive == charging,                       negative == discharging
# so both "discharge/export = positive" flags must default to False.
_E3DC_TOKEN = "e3dc"
_E3DC_GRID_PATTERNS = ("gridpowerconsumption", "grid_power_consumption")
_E3DC_MAIN_PATTERNS = ("batterypowerconsumption", "battery_power_consumption")


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


def _is_power(hass: HomeAssistant, ent: er.RegistryEntry) -> bool:
    """True if the entity looks like a power sensor (device_class or W/kW)."""
    if _device_class(hass, ent) == "power":
        return True
    unit = _unit(hass, ent)
    return bool(unit and unit.strip().lower() in _POWER_UNITS)


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
    """Return the single best candidate's entity_id, or None if ambiguous."""
    if len(entities) == 1:
        return entities[0].entity_id
    narrowed = [e for e in entities if _matches_suffix(e, suffixes)]
    return narrowed[0].entity_id if len(narrowed) == 1 else None


def _pick_preferred(
    entities: list[er.RegistryEntry], preference: tuple[str, ...]
) -> str | None:
    """Pick by *ordered* suffix preference; each step must be unique.

    Tries each suffix in order and returns the first that matches exactly one
    entity. Falls back to the sole candidate when there is only one overall.
    """
    for suffix in preference:
        matches = [e for e in entities if _matches_suffix(e, (suffix,))]
        if len(matches) == 1:
            return matches[0].entity_id
    return entities[0].entity_id if len(entities) == 1 else None


def _manual_option(hass: HomeAssistant, entity_id: str) -> str | None:
    """Best guess for the select option that means 'manual / custom' mode."""
    state = hass.states.get(entity_id)
    if state is None:
        return None
    options = state.attributes.get("options") or []
    if "manual" in options:
        return "manual"
    # Solarbank 3 exposes exactly ["backup", "manual"]; if one is the (useless)
    # backup mode, the other is the usable manual/custom mode.
    if len(options) == 2 and "backup" in options:
        return next(o for o in options if o != "backup")
    return None


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
        if _is_power(hass, ent):
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
    """Pick any energy statistic that identifies the grid device."""
    for key in ("flow_from", "flow_to"):
        for flow in source.get(key) or []:
            stat = flow.get("stat_energy_from") or flow.get("stat_energy_to")
            if stat:
                return stat
    return source.get("stat_energy_from") or source.get("stat_energy_to")


# --- public resolvers --------------------------------------------------------
async def suggested_inputs_from_energy(hass: HomeAssistant) -> dict[str, Any]:
    """Best-effort grid / main-battery suggestions from the Energy Dashboard."""
    out: dict[str, Any] = {}
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


def _e3dc_power_match(
    hass: HomeAssistant,
    sensors: list[er.RegistryEntry],
    patterns: tuple[str, ...],
) -> str | None:
    """The single E3DC power sensor whose entity_id contains one of patterns."""
    candidates = [
        e.entity_id
        for e in sensors
        if any(p in e.entity_id.lower() for p in patterns) and _is_power(hass, e)
    ]
    return candidates[0] if len(candidates) == 1 else None


async def suggested_from_e3dc(hass: HomeAssistant) -> dict[str, Any]:
    """Best-effort roof-system suggestions for an E3DC installation.

    Pattern-based (entity_id) because E3DC is frequently bridged via KNX/RSCP
    without a HA device or energy-dashboard entry, so the device/energy walk in
    :func:`suggested_inputs_from_energy` finds nothing. Also emits the E3DC sign
    convention so the user does not have to reason about it.
    """
    out: dict[str, Any] = {}
    ent_reg = er.async_get(hass)
    sensors = [
        e
        for e in ent_reg.entities.values()
        if e.domain == "sensor" and _E3DC_TOKEN in e.entity_id.lower()
    ]
    if not sensors:
        return out

    grid = _e3dc_power_match(hass, sensors, _E3DC_GRID_PATTERNS)
    if grid:
        out[CONF_GRID_POWER] = grid
        out[CONF_GRID_EXPORT_POSITIVE] = False  # E3DC: positive == grid import

    main = _e3dc_power_match(hass, sensors, _E3DC_MAIN_PATTERNS)
    if main:
        out[CONF_MAIN_POWER] = main
        out[CONF_MAIN_DISCHARGE_POSITIVE] = False  # E3DC: negative == discharge

    return out


def _anker_solarbank_device(hass: HomeAssistant) -> str | None:
    """The controllable anker_solix Solarbank device, or None if ambiguous.

    The integration creates several devices (a virtual system device, the
    Solarbank, possibly an inverter). We prefer the device that carries the
    ``usage_mode`` select (the one we actually steer); failing that, a device
    with a unique battery-SoC sensor, and finally the sole anker_solix device.
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

    for device in anker:
        ents = er.async_entries_for_device(
            ent_reg, device.id, include_disabled_entities=True
        )
        if any(
            e.domain == "select" and _matches_suffix(e, _USAGE_MODE_SUFFIXES)
            for e in ents
        ):
            return device.id

    with_soc = [
        device
        for device in anker
        if _soc_sensor_for_device(hass, ent_reg, device.id) is not None
    ]
    if len(with_soc) == 1:
        return with_soc[0].id
    if len(anker) == 1:
        return anker[0].id
    return None


async def suggested_from_anker(hass: HomeAssistant) -> dict[str, Any]:
    """Best-effort balcony / Anker-control suggestions from anker_solix."""
    out: dict[str, Any] = {}
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

    # Balcony SoC: a battery-% sensor, by ordered preference (avoid exp packs).
    soc_sensors = [
        e
        for e in sensors
        if _device_class(hass, e) == "battery" and _unit(hass, e) == "%"
    ]
    if (val := _pick_preferred(soc_sensors, _SOC_PREFERENCE)) is not None:
        out[CONF_BALCONY_SOC] = val

    # Balcony power: a power sensor; narrow to the "battery power" one.
    power = [e for e in sensors if _is_power(hass, e)]
    narrowed_power = [e for e in power if _matches_suffix(e, _BATTERY_POWER_SUFFIXES)]
    balcony_power = None
    if len(narrowed_power) == 1:
        balcony_power = narrowed_power[0].entity_id
    elif len(power) == 1:
        balcony_power = power[0].entity_id
    if balcony_power is not None:
        out[CONF_BALCONY_POWER] = balcony_power
        # Solarbank ``battery_power`` is negative while discharging.
        out[CONF_BALCONY_DISCHARGE_POSITIVE] = False

    # Usage-mode select (+ the option value that means manual/custom).
    if (val := _pick(selects, _USAGE_MODE_SUFFIXES)) is not None:
        out[CONF_MODE_SELECT] = val
        if (manual := _manual_option(hass, val)) is not None:
            out[CONF_MODE_MANUAL_VALUE] = manual

    # AC-charge enable switch: strict suffix match (no single-switch fallback)
    # so the unrelated AC output socket can never be mis-picked.
    ac_charge_sw = [
        e for e in switches if _matches_suffix(e, _AC_CHARGE_SWITCH_SUFFIXES)
    ]
    if len(ac_charge_sw) == 1:
        out[CONF_AC_CHARGE_SWITCH] = ac_charge_sw[0].entity_id

    # The two W controls (system output for discharge; AC input limit for the
    # charge cap). Disjoint suffix sets + unique-candidate rule make a wrong
    # mapping impossible. The AC-charge limit may be a number OR a stepped select
    # (e.g. Anker `ac_input_limit`), so selects with a W unit are considered too.
    w_numbers = [
        e for e in numbers if (u := _unit(hass, e)) and u.strip().lower() == "w"
    ]
    w_selects = [
        e for e in selects if (u := _unit(hass, e)) and u.strip().lower() == "w"
    ]
    system_out = [e for e in w_numbers if _matches_suffix(e, _SYSTEM_OUTPUT_SUFFIXES)]
    ac_input = [
        e for e in (w_numbers + w_selects) if _matches_suffix(e, _AC_INPUT_SUFFIXES)
    ]
    ambiguous = {e.entity_id for e in system_out} & {e.entity_id for e in ac_input}
    system_out = [e for e in system_out if e.entity_id not in ambiguous]
    ac_input = [e for e in ac_input if e.entity_id not in ambiguous]
    if len(system_out) == 1:
        out[CONF_DISCHARGE_NUMBER] = system_out[0].entity_id
    if len(ac_input) == 1:
        out[CONF_AC_CHARGE_NUMBER] = ac_input[0].entity_id

    return out
