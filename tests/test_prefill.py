"""Tests for the generic, unambiguous-only config-flow prefill."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.balcony_battery_manager import const as C, prefill

W = {"unit_of_measurement": "W", "device_class": "power"}


def _solarbank(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.solarbank_4_soc", "55", {"unit_of_measurement": "%"})
    hass.states.async_set("sensor.solarbank_4_solar_power", "400", W)
    hass.states.async_set("sensor.solarbank_4_ac_output", "200", W)
    hass.states.async_set(
        "select.solarbank_4_grid_flow", "discharge", {"options": ["Charge", "Discharge"]}
    )
    hass.states.async_set("number.solarbank_4_target_grid_power", "0", W)
    hass.states.async_set(
        "sensor.solarbank_4_battery_capacity", "5120", {"unit_of_measurement": "Wh"}
    )


async def test_prefill_solarbank_and_house(hass: HomeAssistant) -> None:
    _solarbank(hass)
    hass.states.async_set("sensor.house_grid_power", "-300", W)
    hass.states.async_set("sensor.house_battery_power", "500", W)
    hass.states.async_set("sun.sun", "above_horizon")
    s = prefill.suggest(hass)
    assert s[C.CONF_SOC_ANKER] == "sensor.solarbank_4_soc"
    assert s[C.CONF_P_ANKER_PV] == "sensor.solarbank_4_solar_power"
    assert s[C.CONF_P_ANKER_OUT] == "sensor.solarbank_4_ac_output"
    assert s[C.CONF_GRID_FLOW_SELECT] == "select.solarbank_4_grid_flow"
    assert s[C.CONF_GRID_FLOW_DISCHARGE] == "Discharge"
    assert s[C.CONF_GRID_FLOW_CHARGE] == "Charge"
    assert s[C.CONF_TARGET_POWER_NUMBER] == "number.solarbank_4_target_grid_power"
    assert s[C.CONF_CAPACITY_KWH] == 5.12
    assert s[C.CONF_P_GRID] == "sensor.house_grid_power"
    assert s[C.CONF_P_BATT_DRAW] == "sensor.house_battery_power"
    assert s[C.CONF_SUN] == "sun.sun"
    # never guessed: sign conventions and the optional main-battery SoC
    assert C.CONF_GRID_EXPORT_POSITIVE not in s
    assert C.CONF_BATT_DRAW_POSITIVE not in s
    assert C.CONF_MAIN_SOC not in s


async def test_prefill_ambiguous_leaves_field_empty(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.grid_import_power", "0", W)
    hass.states.async_set("sensor.grid_export_power", "0", W)
    hass.states.async_set("sensor.solarbank_4_soc", "55", {"unit_of_measurement": "%"})
    hass.states.async_set("sensor.solarbank_4_e1_soc", "40", {"unit_of_measurement": "%"})
    s = prefill.suggest(hass)
    assert C.CONF_P_GRID not in s
    assert C.CONF_SOC_ANKER not in s


async def test_prefill_ignores_non_power_units(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.grid_voltage", "230", {"unit_of_measurement": "V"})
    hass.states.async_set("sensor.grid_power", "1.2", {"unit_of_measurement": "kW"})
    assert prefill.suggest(hass)[C.CONF_P_GRID] == "sensor.grid_power"


async def test_prefill_uses_registry_platform(hass: HomeAssistant) -> None:
    """Entities of the Anker platform count as Solarbank even without the name."""
    ent_reg = er.async_get(hass)
    entry = ent_reg.async_get_or_create(
        "number", "anker_solix_official", "abc", suggested_object_id="sb_target_grid_power"
    )
    hass.states.async_set(entry.entity_id, "0", W)
    assert prefill.suggest(hass)[C.CONF_TARGET_POWER_NUMBER] == entry.entity_id
