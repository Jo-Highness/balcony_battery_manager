"""Common fixtures for Balcony Battery Manager tests."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.balcony_battery_manager.const import (
    CONF_AC_CHARGE_NUMBER,
    CONF_AC_CHARGE_SWITCH,
    CONF_BALCONY_POWER,
    CONF_BALCONY_SOC,
    CONF_CHARGE_HEADROOM,
    CONF_DEADBAND,
    CONF_DISCHARGE_NUMBER,
    CONF_DISCHARGE_OFF_THRESHOLD,
    CONF_DISCHARGE_ON_THRESHOLD,
    CONF_DISCHARGE_SHARE,
    CONF_GRID_POWER,
    CONF_INTERVAL,
    CONF_MAIN_POWER,
    CONF_MAIN_SOC,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_HOUSE_FEED,
    CONF_MODE_MANUAL_VALUE,
    CONF_MODE_SELECT,
    DOMAIN,
)
from custom_components.balcony_battery_manager.coordinator import (
    BalconyBatteryCoordinator,
)

GRID = "sensor.grid_power"
MAIN_SOC = "sensor.main_soc"
MAIN_POWER = "sensor.main_power"
BALCONY_SOC = "sensor.balcony_soc"
BALCONY_POWER = "sensor.balcony_power"
MODE_SELECT = "select.anker_usage_mode"
DISCHARGE_NUMBER = "number.anker_output_preset"
AC_CHARGE_SWITCH = "switch.anker_ac_charge"
AC_CHARGE_NUMBER = "number.anker_ac_charge_power"
MANUAL_VALUE = "manual"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def build_data(**overrides: Any) -> dict[str, Any]:
    data = {
        CONF_GRID_POWER: GRID,
        CONF_MAIN_SOC: MAIN_SOC,
        CONF_MAIN_POWER: MAIN_POWER,
        CONF_BALCONY_SOC: BALCONY_SOC,
        CONF_BALCONY_POWER: BALCONY_POWER,
        CONF_MODE_SELECT: MODE_SELECT,
        CONF_MODE_MANUAL_VALUE: MANUAL_VALUE,
        CONF_DISCHARGE_NUMBER: DISCHARGE_NUMBER,
        CONF_AC_CHARGE_SWITCH: AC_CHARGE_SWITCH,
        CONF_AC_CHARGE_NUMBER: AC_CHARGE_NUMBER,
        CONF_MAX_CHARGE_POWER: 1100,
        CONF_MAX_HOUSE_FEED: 800,
        CONF_INTERVAL: 300,
        CONF_CHARGE_HEADROOM: 200,
        CONF_DISCHARGE_ON_THRESHOLD: 400,
        CONF_DISCHARGE_OFF_THRESHOLD: 100,
        CONF_DISCHARGE_SHARE: 50,
        CONF_DEADBAND: 25,
    }
    data.update(overrides)
    return data


@pytest.fixture
def make_coordinator(
    hass,
) -> Callable[..., Coroutine[Any, Any, BalconyBatteryCoordinator]]:
    async def _factory(**overrides: Any) -> BalconyBatteryCoordinator:
        entry = MockConfigEntry(domain=DOMAIN, data=build_data(**overrides))
        entry.add_to_hass(hass)
        coordinator = BalconyBatteryCoordinator(hass, entry)
        await coordinator._async_restore()
        return coordinator

    return _factory


def set_inputs(
    hass,
    *,
    grid: Any = 0,
    main_soc: Any = 50,
    main_power: Any = 0,
    balcony_soc: Any = 50,
    balcony_power: Any = 0,
) -> None:
    """Push a full set of input sensor states."""
    hass.states.async_set(GRID, grid)
    hass.states.async_set(MAIN_SOC, main_soc)
    hass.states.async_set(MAIN_POWER, main_power)
    hass.states.async_set(BALCONY_SOC, balcony_soc)
    hass.states.async_set(BALCONY_POWER, balcony_power)
