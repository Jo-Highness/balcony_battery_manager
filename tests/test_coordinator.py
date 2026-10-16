"""Coordinator tests: unit handling, actuator write order, safety paths."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from unittest.mock import patch

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.balcony_battery_manager import const as C, logic, units
from custom_components.balcony_battery_manager.coordinator import BalconyBatteryCoordinator

from .conftest import FULL_DATA, Actuators, set_sensors


def _coord(hass: HomeAssistant, **opts) -> BalconyBatteryCoordinator:
    entry = MockConfigEntry(
        domain=C.DOMAIN,
        version=C.CONFIG_VERSION,
        minor_version=C.CONFIG_MINOR_VERSION,
        data={},
        options={**FULL_DATA, **opts},
    )
    entry.add_to_hass(hass)
    return BalconyBatteryCoordinator(hass, entry)


def _dec(flow: str, power: float, mode: str | None = None) -> logic.Decision:
    mode = mode or (flow if flow else logic.MODE_IDLE)
    return logic.Decision(mode=mode, grid_flow=flow, target_power=power)


# ---------------------------------------------------------------- units


def test_units_convert() -> None:
    assert units.convert(1.5, "kW", units.POWER_TO_W) == 1500.0
    assert units.convert(2, "MW", units.POWER_TO_W) == 2_000_000.0
    assert units.convert(300, "W", units.POWER_TO_W) == 300.0
    assert units.convert(300, None, units.POWER_TO_W) == 300.0
    assert units.convert(300, "A", units.POWER_TO_W) is None
    assert units.convert(5000, "Wh", units.ENERGY_TO_KWH) == 5.0
    assert units.convert(50, "%", units.PERCENT) == 50
    assert units.convert(50, "W", units.PERCENT) is None


async def test_kw_sensor_read_as_watts(hass: HomeAssistant) -> None:
    coord = _coord(hass)
    hass.states.async_set(FULL_DATA[C.CONF_P_GRID], "1.5", {"unit_of_measurement": "kW"})
    assert coord._num(C.CONF_P_GRID) == 1500.0
    hass.states.async_set(FULL_DATA[C.CONF_P_GRID], "0.2", {"unit_of_measurement": "MW"})
    assert coord._num(C.CONF_P_GRID) == 200_000.0


async def test_unknown_unit_is_unavailable_and_warned_once(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    coord = _coord(hass)
    hass.states.async_set(FULL_DATA[C.CONF_P_GRID], "3", {"unit_of_measurement": "A"})
    with caplog.at_level(logging.WARNING):
        assert coord._num(C.CONF_P_GRID) is None
        assert coord._num(C.CONF_P_GRID) is None
    assert caplog.text.count("unsupported unit") == 1
    # SoC in a non-% unit is rejected as well
    hass.states.async_set(FULL_DATA[C.CONF_SOC_ANKER], "50", {"unit_of_measurement": "W"})
    assert coord._num(C.CONF_SOC_ANKER) is None


async def test_unknown_unit_triggers_failsafe(hass: HomeAssistant, actuators: Actuators) -> None:
    coord = _coord(hass)
    set_sensors(hass, **{C.CONF_P_GRID: ("1", "A")})
    data = await coord._cycle()
    assert data[C.KEY_MODE] == logic.MODE_FAILSAFE


async def test_sign_normalisation(hass: HomeAssistant) -> None:
    coord = _coord(hass, **{C.CONF_BATT_DRAW_POSITIVE: False, C.CONF_GRID_EXPORT_POSITIVE: True})
    hass.states.async_set(FULL_DATA[C.CONF_P_BATT_DRAW], "-0.5", {"unit_of_measurement": "kW"})
    hass.states.async_set(FULL_DATA[C.CONF_P_GRID], "-200", {"unit_of_measurement": "W"})
    assert coord._signed(C.CONF_P_BATT_DRAW, C.CONF_BATT_DRAW_POSITIVE, True, True) == 500.0
    assert coord._signed(C.CONF_P_GRID, C.CONF_GRID_EXPORT_POSITIVE, True, True) == -200.0


# ---------------------------------------------------------------- _apply


async def test_direction_change_order(hass: HomeAssistant) -> None:
    """Charge -> discharge: power 0, then switch direction, then new setpoint."""
    act = Actuators(hass).setup(number="500", select="charge")
    coord = _coord(hass)
    coord._last_written = ("charge", 500.0)
    applied = await coord._apply(_dec("discharge", 300))
    assert act.calls == [("number", 0), ("select", "discharge"), ("number", 300)]
    assert applied == 300.0
    assert coord._last_written == ("discharge", 300.0)


async def test_unknown_device_state_zeroes_before_switch(hass: HomeAssistant) -> None:
    act = Actuators(hass).setup(number="0", select="discharge")
    coord = _coord(hass)  # _last_written None after start
    await coord._apply(_dec("charge", 400))
    assert act.calls == [("number", 0), ("select", "charge"), ("number", 400)]


async def test_same_direction_writes_power_only(hass: HomeAssistant, actuators) -> None:
    coord = _coord(hass)
    await coord._apply(_dec("discharge", 350))
    assert actuators.calls == [("number", 350)]


async def test_deadband(hass: HomeAssistant, actuators) -> None:
    coord = _coord(hass)
    await coord._apply(_dec("discharge", 300))
    actuators.calls.clear()
    assert await coord._apply(_dec("discharge", 310)) == 300.0  # below deadband
    assert actuators.calls == []
    await coord._apply(_dec("discharge", 330))
    assert actuators.calls == [("number", 330)]


async def test_idle_writes_zero_once(hass: HomeAssistant, actuators) -> None:
    coord = _coord(hass)
    await coord._apply(_dec("discharge", 300))
    actuators.calls.clear()
    await coord._apply(_dec("", 0))
    await coord._apply(_dec("", 0))
    assert actuators.calls == [("number", 0)]


async def test_clamped_to_number_max(hass: HomeAssistant, actuators) -> None:
    coord = _coord(hass)
    assert await coord._apply(_dec("discharge", 2000)) == 800.0
    assert actuators.calls == [("number", 800)]


async def test_kw_number_is_scaled(hass: HomeAssistant) -> None:
    act = Actuators(hass)
    act.number_attrs = {"min": 0, "max": 0.8, "step": 0.01, "unit_of_measurement": "kW"}
    act.setup()
    coord = _coord(hass)
    assert await coord._apply(_dec("discharge", 2000)) == 800.0
    assert act.calls == [("number", 0.8)]


async def test_number_with_unsupported_unit_only_gets_zero(hass: HomeAssistant) -> None:
    act = Actuators(hass)
    act.number_attrs = {"min": 0, "max": 100, "unit_of_measurement": "%"}
    act.setup()
    coord = _coord(hass)
    assert await coord._apply(_dec("discharge", 300)) == 0.0
    assert act.calls == [("number", 0)]


async def test_failed_write_falls_back_to_zero(hass: HomeAssistant) -> None:
    act = Actuators(hass).setup(number="0", select="charge")
    act.fail.add("select")
    coord = _coord(hass)
    coord._last_written = ("", 0.0)
    assert await coord._apply(_dec("discharge", 300)) == 0.0
    assert act.calls == [("select", "discharge"), ("number", 0)]
    assert coord._last_written == ("", 0.0)


async def test_timeout_falls_back_to_zero(hass: HomeAssistant, actuators) -> None:
    async def slow(call: ServiceCall) -> None:
        actuators.calls.append(("select", call.data["option"]))
        await asyncio.sleep(1)

    hass.services.async_register("select", "select_option", slow)
    hass.states.async_set(Actuators.SELECT, "charge", actuators.select_attrs)
    coord = _coord(hass)
    coord._last_written = ("", 0.0)
    with patch.object(C, "SERVICE_TIMEOUT", 0.01):
        assert await coord._apply(_dec("discharge", 300)) == 0.0
    assert actuators.calls[-1] == ("number", 0)


async def test_unavailable_number_is_not_written(hass: HomeAssistant, actuators) -> None:
    hass.states.async_set(Actuators.NUMBER, "unavailable")
    coord = _coord(hass)
    assert await coord._apply(_dec("discharge", 300)) == 0.0
    assert actuators.calls == []
    assert coord._last_written is None


async def test_control_mode_selected_before_power(hass: HomeAssistant, actuators) -> None:
    coord = _coord(
        hass,
        **{C.CONF_MODE_SELECT: "select.anker_mode", C.CONF_CONTROL_MODE: "third_party"},
    )
    await coord._apply(_dec("discharge", 300))
    assert actuators.calls == [("mode", "third_party"), ("number", 300)]


# ---------------------------------------------------------------- cycle


def _charge_scenario(hass: HomeAssistant) -> None:
    """Big export, low PV, half-empty Solarbank -> charge from surplus."""
    set_sensors(
        hass,
        **{
            C.CONF_P_BATT_DRAW: ("0", "W"),
            C.CONF_P_GRID: ("3", "kW"),  # 3000 W export (positive = export)
            C.CONF_SOC_ANKER: ("20", "%"),
            C.CONF_P_ANKER_PV: ("50", "W"),
        },
    )
    sunset = dt_util.utcnow() + timedelta(hours=2)
    hass.states.async_set("sun.sun", "above_horizon", {"next_setting": sunset.isoformat()})


async def test_charge_integrator_capped_at_device_max(hass: HomeAssistant, actuators) -> None:
    """No wind-up beyond the number's max even with max_charge 2500 W."""
    _charge_scenario(hass)
    coord = _coord(hass)
    for _ in range(5):
        data = await coord._cycle()
    assert data[C.KEY_MODE] == logic.MODE_CHARGE
    assert data[C.KEY_TARGET_POWER] == 800.0
    assert coord._state.last_charge_w == 800.0
    assert ("select", "charge") in actuators.calls


async def test_integrator_frozen_when_write_fails(hass: HomeAssistant, actuators) -> None:
    _charge_scenario(hass)
    actuators.fail.add("number")
    coord = _coord(hass)
    for _ in range(3):
        await coord._cycle()
    assert coord._state.last_charge_w == 0.0


async def test_failsafe_resets_staircase(hass: HomeAssistant, actuators) -> None:
    coord = _coord(hass)
    coord._state.discharge.step_index = 2
    coord._state.discharge.up_timers = [500.0, 500.0]
    data = await coord._cycle()  # no sensors -> failsafe
    assert data[C.KEY_MODE] == logic.MODE_FAILSAFE
    assert coord._state.discharge.step_index == 0
    assert coord._state.discharge.up_timers == []


async def test_first_cycle_uses_configured_interval(hass: HomeAssistant, actuators) -> None:
    set_sensors(hass)
    coord = _coord(hass, **{C.CONF_INTERVAL: 60})
    seen = []
    real = logic.decide

    def spy(*args, **kwargs):
        seen.append(kwargs["dt_s"])
        return real(*args, **kwargs)

    with patch.object(logic, "decide", spy):
        await coord._cycle()
    assert seen == [60.0]


async def test_sunset_from_sun_entity_and_fallback(hass: HomeAssistant) -> None:
    coord = _coord(hass)
    now = dt_util.utcnow()
    nxt = now + timedelta(hours=3)
    hass.states.async_set("sun.sun", "above_horizon", {"next_setting": nxt.isoformat()})
    assert abs((coord._sunset(now) - nxt).total_seconds()) < 1
    hass.states.async_remove("sun.sun")
    # astral calculation from the HA home location
    sunset = coord._sunset(now)
    assert now < sunset <= now + timedelta(days=1, hours=1)
    with patch(
        "custom_components.balcony_battery_manager.coordinator.get_astral_event_next",
        side_effect=ValueError,
    ):
        fallback = dt_util.as_local(coord._sunset(now))
    assert fallback.hour == C.FALLBACK_SUNSET_HOUR


# ---------------------------------------------------------------- disable


async def test_disable_zeroes_and_restores_mode(hass: HomeAssistant, actuators) -> None:
    coord = _coord(
        hass,
        **{
            C.CONF_MODE_SELECT: "select.anker_mode",
            C.CONF_CONTROL_MODE: "third_party",
            C.CONF_RESTORE_MODE: "self_consumption",
        },
    )
    await coord._apply(_dec("discharge", 300))
    actuators.calls.clear()
    await coord.async_disable()
    assert actuators.calls == [("number", 0), ("mode", "self_consumption")]
    assert coord.data[C.KEY_MODE] == C.MODE_DISABLED
    # a cycle after disabling writes nothing
    actuators.calls.clear()
    data = await coord._cycle()
    assert data[C.KEY_MODE] == C.MODE_DISABLED
    assert actuators.calls == []


async def test_disable_waits_for_running_cycle(hass: HomeAssistant, actuators) -> None:
    coord = _coord(hass)
    await coord._lock.acquire()
    task = hass.async_create_task(coord.async_disable())
    await asyncio.sleep(0)
    assert not task.done()
    assert coord.enabled is True  # disable did not run inside the cycle
    coord._lock.release()
    await task
    assert coord.enabled is False
    assert actuators.calls[-1] == ("number", 0)
