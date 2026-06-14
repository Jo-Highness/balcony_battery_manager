"""Tests for the best-effort config-flow pre-fill resolvers."""

from __future__ import annotations

from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.balcony_battery_manager.const import (
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
from custom_components.balcony_battery_manager.prefill import (
    suggested_from_anker,
    suggested_inputs_from_energy,
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _device(hass, domain: str, ident: str):
    config_entry = MockConfigEntry(domain=domain)
    config_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(domain, ident)},
    )
    return device


def _add(
    hass,
    *,
    domain: str,
    platform: str,
    unique_id: str,
    object_id: str,
    device_id: str,
    device_class: str | None = None,
    unit: str | None = None,
    translation_key: str | None = None,
    state: str = "0",
) -> str:
    """Register an entity and give it a matching live state, return entity_id."""
    entry = er.async_get(hass).async_get_or_create(
        domain,
        platform,
        unique_id,
        suggested_object_id=object_id,
        device_id=device_id,
        original_device_class=device_class,
        translation_key=translation_key,
    )
    attrs: dict[str, str] = {}
    if device_class:
        attrs["device_class"] = device_class
    if unit:
        attrs["unit_of_measurement"] = unit
    hass.states.async_set(entry.entity_id, state, attrs)
    return entry.entity_id


class _Manager:
    def __init__(self, data):
        self.data = data


def _patch_energy(data):
    async def _get(hass):
        return _Manager(data)

    return patch(
        "homeassistant.components.energy.data.async_get_manager", _get
    )


# --------------------------------------------------------------------------- #
# Feature 1: energy-dashboard prefill
# --------------------------------------------------------------------------- #
async def test_energy_prefill_grid_and_main(hass):
    grid_dev = _device(hass, "e3dc", "grid")
    grid_kwh = _add(
        hass, domain="sensor", platform="e3dc", unique_id="g_kwh",
        object_id="e3dc_grid_kwh", device_id=grid_dev.id,
        device_class="energy", unit="kWh",
    )
    grid_power = _add(
        hass, domain="sensor", platform="e3dc", unique_id="g_pwr",
        object_id="e3dc_grid_power", device_id=grid_dev.id,
        device_class="power", unit="W",
    )

    batt_dev = _device(hass, "e3dc", "batt")
    batt_kwh = _add(
        hass, domain="sensor", platform="e3dc", unique_id="b_kwh",
        object_id="e3dc_batt_kwh", device_id=batt_dev.id,
        device_class="energy", unit="kWh",
    )
    batt_power = _add(
        hass, domain="sensor", platform="e3dc", unique_id="b_pwr",
        object_id="e3dc_batt_power", device_id=batt_dev.id,
        device_class="power", unit="W",
    )
    batt_soc = _add(
        hass, domain="sensor", platform="e3dc", unique_id="b_soc",
        object_id="e3dc_batt_soc", device_id=batt_dev.id,
        device_class="battery", unit="%", state="50",
    )

    data = {
        "energy_sources": [
            {
                "type": "grid",
                "flow_from": [{"stat_energy_from": grid_kwh}],
                "flow_to": [{"stat_energy_to": None}],
            },
            {"type": "battery", "stat_energy_from": batt_kwh, "stat_energy_to": None},
            {"type": "solar", "stat_energy_from": "sensor.pv"},
        ]
    }
    with _patch_energy(data):
        result = await suggested_inputs_from_energy(hass)

    assert result[CONF_GRID_POWER] == grid_power
    assert result[CONF_MAIN_POWER] == batt_power
    assert result[CONF_MAIN_SOC] == batt_soc


async def test_energy_prefill_ambiguous_power_yields_nothing(hass):
    grid_dev = _device(hass, "e3dc", "grid")
    grid_kwh = _add(
        hass, domain="sensor", platform="e3dc", unique_id="g_kwh",
        object_id="e3dc_grid_kwh", device_id=grid_dev.id,
        device_class="energy", unit="kWh",
    )
    # Two power sensors on the same device -> not unambiguous -> no suggestion.
    _add(
        hass, domain="sensor", platform="e3dc", unique_id="p1",
        object_id="e3dc_p1", device_id=grid_dev.id, device_class="power", unit="W",
    )
    _add(
        hass, domain="sensor", platform="e3dc", unique_id="p2",
        object_id="e3dc_p2", device_id=grid_dev.id, device_class="power", unit="W",
    )

    data = {"energy_sources": [
        {"type": "grid", "flow_from": [{"stat_energy_from": grid_kwh}]}
    ]}
    with _patch_energy(data):
        result = await suggested_inputs_from_energy(hass)

    assert CONF_GRID_POWER not in result


async def test_energy_prefill_no_manager(hass):
    async def _raise(hass):
        raise RuntimeError("energy not configured")

    with patch(
        "homeassistant.components.energy.data.async_get_manager", _raise
    ):
        assert await suggested_inputs_from_energy(hass) == {}


# --------------------------------------------------------------------------- #
# Feature 2: anker_solix prefill
# --------------------------------------------------------------------------- #
async def test_anker_prefill_resolves_controls(hass):
    dev = _device(hass, "anker_solix", "solarbank1")
    soc = _add(
        hass, domain="sensor", platform="anker_solix", unique_id="sn_soc",
        object_id="anker_state_of_charge", device_id=dev.id,
        device_class="battery", unit="%", translation_key="state_of_charge",
        state="100",
    )
    batt_power = _add(
        hass, domain="sensor", platform="anker_solix", unique_id="sn_bp",
        object_id="anker_battery_power", device_id=dev.id,
        device_class="power", unit="W", translation_key="battery_power",
    )
    # A second power sensor forces the suffix-narrowing path.
    _add(
        hass, domain="sensor", platform="anker_solix", unique_id="sn_sp",
        object_id="anker_solar_power", device_id=dev.id,
        device_class="power", unit="W", translation_key="solar_power",
    )
    mode = _add(
        hass, domain="select", platform="anker_solix", unique_id="sn_mode",
        object_id="anker_usage_mode", device_id=dev.id,
        translation_key="usage_mode", state="manual",
    )
    socket = _add(
        hass, domain="switch", platform="anker_solix", unique_id="sn_sock",
        object_id="anker_ac_socket", device_id=dev.id,
        translation_key="ac_socket", state="off",
    )
    sys_out = _add(
        hass, domain="number", platform="anker_solix", unique_id="sn_out",
        object_id="anker_system_output", device_id=dev.id, unit="W",
        translation_key="system_output_power", state="0",
    )
    ac_in = _add(
        hass, domain="number", platform="anker_solix", unique_id="sn_acin",
        object_id="anker_ac_input_limit", device_id=dev.id, unit="W",
        translation_key="ac_input_limit", state="1200",
    )

    result = await suggested_from_anker(hass)

    assert result[CONF_BALCONY_SOC] == soc
    assert result[CONF_BALCONY_POWER] == batt_power
    assert result[CONF_MODE_SELECT] == mode
    assert result[CONF_AC_CHARGE_SWITCH] == socket
    assert result[CONF_DISCHARGE_NUMBER] == sys_out
    assert result[CONF_AC_CHARGE_NUMBER] == ac_in


async def test_anker_prefill_ambiguous_numbers_left_blank(hass):
    dev = _device(hass, "anker_solix", "solarbank1")
    _add(
        hass, domain="sensor", platform="anker_solix", unique_id="sn_soc",
        object_id="anker_state_of_charge", device_id=dev.id,
        device_class="battery", unit="%", translation_key="state_of_charge",
        state="80",
    )
    # Two W-numbers that both match the system-output set -> ambiguous.
    _add(
        hass, domain="number", platform="anker_solix", unique_id="sn_o1",
        object_id="anker_output_power", device_id=dev.id, unit="W",
        translation_key="output_power",
    )
    _add(
        hass, domain="number", platform="anker_solix", unique_id="sn_o2",
        object_id="anker_system_output_power", device_id=dev.id, unit="W",
        translation_key="system_output_power",
    )

    result = await suggested_from_anker(hass)

    assert CONF_DISCHARGE_NUMBER not in result
    assert CONF_AC_CHARGE_NUMBER not in result


async def test_anker_prefill_no_device(hass):
    assert await suggested_from_anker(hass) == {}
