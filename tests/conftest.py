"""Shared fixtures for the Balcony Battery Manager tests."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.balcony_battery_manager import config_flow, const as C

# A complete, schema-valid set of config-flow answers. Entity fields are plain
# entity-id strings (the selectors validate the id/domain, not existence).
FULL_DATA: dict = {
    # inputs
    C.CONF_P_BATT_DRAW: "sensor.batt_draw",
    C.CONF_BATT_DRAW_POSITIVE: True,
    C.CONF_P_ANKER_OUT: "sensor.anker_out",
    C.CONF_P_GRID: "sensor.grid",
    C.CONF_GRID_EXPORT_POSITIVE: True,
    C.CONF_SOC_ANKER: "sensor.anker_soc",
    C.CONF_P_ANKER_PV: "sensor.anker_pv",
    C.CONF_SUN: "sun.sun",
    # actors
    C.CONF_GRID_FLOW_SELECT: "select.grid_flow",
    C.CONF_GRID_FLOW_DISCHARGE: "discharge",
    C.CONF_GRID_FLOW_CHARGE: "charge",
    C.CONF_TARGET_POWER_NUMBER: "number.target_power",
    # discharge staircase
    C.CONF_DISCHARGE_TH1: 800.0,
    C.CONF_DISCHARGE_TH2: 1600.0,
    C.CONF_DISCHARGE_STAGE1: 350.0,
    C.CONF_DISCHARGE_STAGE2: 800.0,
    C.CONF_DWELL_MINUTES: 10.0,
    C.CONF_HYSTERESIS: 100.0,
    # charging
    C.CONF_MAX_CHARGE: 2500.0,
    C.CONF_SURPLUS_RESERVE: 100.0,
    C.CONF_TARGET_SOC: 100.0,
    C.CONF_CAPACITY_KWH: 15.5,
    C.CONF_PV_NOMINAL_W: 2000.0,
    C.CONF_AFTERNOON_HOUR: 13.0,
    C.CONF_AFTERNOON_FACTOR: 0.33,
    # grid support
    C.CONF_GRID_SUPPORT_ENABLED: True,
    C.CONF_MAIN_EMPTY_SOC: 10.0,
    C.CONF_MAIN_EMPTY_SOC_HYST: 3.0,
    C.CONF_GRID_SUPPORT_MARGIN: 100.0,
    C.CONF_GRID_SUPPORT_MAX: 800.0,
    C.CONF_MIN_DISCHARGE_SOC: 10.0,
    # general
    C.CONF_INTERVAL: 30.0,
    C.CONF_DEADBAND: 25.0,
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the custom integration in every test."""
    yield


def nest(flat: dict[str, Any]) -> dict[str, Any]:
    """Flat option dict -> sectioned config-flow input."""
    out: dict[str, Any] = {}
    for name, fields in config_flow._section_schemas({}).items():
        keys = [str(marker) for marker in fields]
        out[name] = {k: flat[k] for k in keys if k in flat}
    return out


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A fully configured v2.2 entry (settings in options)."""
    return MockConfigEntry(
        domain=C.DOMAIN,
        title="Balcony Battery Manager",
        version=C.CONFIG_VERSION,
        minor_version=C.CONFIG_MINOR_VERSION,
        unique_id=FULL_DATA[C.CONF_TARGET_POWER_NUMBER],
        data={},
        options=dict(FULL_DATA),
    )


class Actuators:
    """Fake Solarbank actuator entities with a shared, ordered call log."""

    NUMBER = FULL_DATA[C.CONF_TARGET_POWER_NUMBER]
    SELECT = FULL_DATA[C.CONF_GRID_FLOW_SELECT]

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.calls: list[tuple[str, Any]] = []
        self.fail: set[str] = set()
        self.number_attrs: dict[str, Any] = {
            "min": 0,
            "max": 800,
            "step": 1,
            "unit_of_measurement": "W",
        }
        self.select_attrs: dict[str, Any] = {"options": ["discharge", "charge"]}
        self.mode_attrs: dict[str, Any] = {"options": ["third_party", "self_consumption"]}

    def setup(self, number: str = "0", select: str = "discharge") -> Actuators:
        self.hass.states.async_set(self.NUMBER, number, self.number_attrs)
        self.hass.states.async_set(self.SELECT, select, self.select_attrs)
        self.hass.states.async_set("select.anker_mode", "self_consumption", self.mode_attrs)

        async def set_value(call: ServiceCall) -> None:
            self.calls.append(("number", call.data["value"]))
            if "number" in self.fail:
                raise HomeAssistantError("number failed")
            self.hass.states.async_set(
                call.data["entity_id"], str(call.data["value"]), self.number_attrs
            )

        async def select_option(call: ServiceCall) -> None:
            eid = call.data["entity_id"]
            self.calls.append(("select" if eid == self.SELECT else "mode", call.data["option"]))
            if "select" in self.fail:
                raise HomeAssistantError("select failed")
            attrs = self.select_attrs if eid == self.SELECT else self.mode_attrs
            self.hass.states.async_set(eid, call.data["option"], attrs)

        self.hass.services.async_register("number", "set_value", set_value)
        self.hass.services.async_register("select", "select_option", select_option)
        return self


@pytest.fixture
def actuators(hass: HomeAssistant) -> Actuators:
    """Fake number/select actuators (registered services + states)."""
    return Actuators(hass).setup()


def set_sensors(hass: HomeAssistant, **values: Any) -> None:
    """Set the five required input sensors (W / %), overridable per key."""
    defaults = {
        C.CONF_P_BATT_DRAW: ("100", "W"),
        C.CONF_P_ANKER_OUT: ("0", "W"),
        C.CONF_P_GRID: ("0", "W"),
        C.CONF_SOC_ANKER: ("50", "%"),
        C.CONF_P_ANKER_PV: ("300", "W"),
    }
    defaults.update(values)
    for key, (state, unit) in defaults.items():
        hass.states.async_set(FULL_DATA[key], state, {"unit_of_measurement": unit})
