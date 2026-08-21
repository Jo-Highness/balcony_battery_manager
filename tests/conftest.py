"""Shared fixtures for the Balcony Battery Manager tests."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.balcony_battery_manager import const as C

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


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A fully configured v2 entry."""
    return MockConfigEntry(
        domain=C.DOMAIN,
        title="Balcony Battery Manager",
        version=C.CONFIG_VERSION,
        data=dict(FULL_DATA),
    )
