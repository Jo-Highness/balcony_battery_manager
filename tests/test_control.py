"""Integration-style tests: full control cycle, dead-band, fail-safe, restart."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.balcony_battery_manager.const import (
    DOMAIN,
    MODE_CHARGING,
    MODE_DISCHARGING,
    MODE_IDLE,
)
from custom_components.balcony_battery_manager.coordinator import (
    BalconyBatteryCoordinator,
)
from tests.conftest import (
    AC_CHARGE_NUMBER,
    AC_CHARGE_SWITCH,
    DISCHARGE_NUMBER,
    MANUAL_VALUE,
    MODE_SELECT,
    build_data,
    set_inputs,
)


def _mock_all(hass):
    return {
        "number": async_mock_service(hass, "number", "set_value"),
        "select": async_mock_service(hass, "select", "select_option"),
        "switch_on": async_mock_service(hass, "switch", "turn_on"),
        "switch_off": async_mock_service(hass, "switch", "turn_off"),
    }


def _prime_control_entities(hass, *, mode="smart", switch="off"):
    hass.states.async_set(MODE_SELECT, mode)
    hass.states.async_set(DISCHARGE_NUMBER, 0)
    hass.states.async_set(AC_CHARGE_NUMBER, 0)
    hass.states.async_set(AC_CHARGE_SWITCH, switch)


async def test_full_charging_cycle_sends_commands(make_coordinator, hass):
    calls = _mock_all(hass)
    _prime_control_entities(hass, mode="smart", switch="off")
    set_inputs(hass, grid=600, main_power=0, balcony_soc=40)
    await hass.async_block_till_done()

    c = await make_coordinator()
    await c.async_recalculate_now()
    await hass.async_block_till_done()

    assert c.mode == MODE_CHARGING
    # Mode forced to manual.
    assert calls["select"][-1].data["option"] == MANUAL_VALUE
    # AC charge switched on.
    assert len(calls["switch_on"]) == 1
    # AC charge power set to surplus - headroom = 600 - 200 = 400.
    number_targets = {
        call.data["entity_id"]: call.data["value"] for call in calls["number"]
    }
    assert number_targets[AC_CHARGE_NUMBER] == 400


async def test_deadband_prevents_double_send(make_coordinator, hass):
    calls = _mock_all(hass)
    _prime_control_entities(hass, mode=MANUAL_VALUE, switch="on")
    set_inputs(hass, grid=600, main_power=0, balcony_soc=40)
    await hass.async_block_till_done()

    c = await make_coordinator()
    await c.async_recalculate_now()
    await hass.async_block_till_done()
    first = len([cc for cc in calls["number"] if cc.data["entity_id"] == AC_CHARGE_NUMBER])
    assert first == 1

    # Steady state: our 400 W charging now hides 400 W of the original 600 W
    # export, so the meter reads ~200 W. The reconstruction (200 + 400) yields
    # the same 400 W target -> dead-band suppresses a second identical command.
    set_inputs(hass, grid=200, main_power=0, balcony_soc=40)
    await hass.async_block_till_done()
    await c.async_recalculate_now()
    await hass.async_block_till_done()
    second = len([cc for cc in calls["number"] if cc.data["entity_id"] == AC_CHARGE_NUMBER])
    assert second == 1


async def test_discharge_cycle(make_coordinator, hass):
    calls = _mock_all(hass)
    _prime_control_entities(hass, mode="smart", switch="off")
    set_inputs(hass, grid=-50, main_power=450, balcony_soc=80)
    await hass.async_block_till_done()

    c = await make_coordinator()
    await c.async_recalculate_now()
    await hass.async_block_till_done()

    assert c.mode == MODE_DISCHARGING
    number_targets = {
        call.data["entity_id"]: call.data["value"] for call in calls["number"]
    }
    assert number_targets[DISCHARGE_NUMBER] == 225  # 450 * 0.5


async def test_grid_support_cycle(make_coordinator, hass):
    """Main empty + grid import -> balcony discharges to cover the import."""
    calls = _mock_all(hass)
    _prime_control_entities(hass, mode="smart", switch="off")
    # main_soc = 5 % (empty), main not discharging, importing 300 W from grid.
    set_inputs(hass, grid=-300, main_soc=5, main_power=0, balcony_soc=75)
    await hass.async_block_till_done()

    c = await make_coordinator()
    await c.async_recalculate_now()
    await hass.async_block_till_done()

    assert c.mode == MODE_DISCHARGING
    number_targets = {
        call.data["entity_id"]: call.data["value"] for call in calls["number"]
    }
    assert number_targets[DISCHARGE_NUMBER] == 300


async def test_failsafe_holds_last_state(make_coordinator, hass):
    calls = _mock_all(hass)
    _prime_control_entities(hass, mode=MANUAL_VALUE, switch="on")
    set_inputs(hass, grid=600, main_power=0, balcony_soc=40)
    await hass.async_block_till_done()

    c = await make_coordinator()
    await c.async_recalculate_now()
    await hass.async_block_till_done()
    assert c.mode == MODE_CHARGING
    sent_before = c._last_sent_charge

    # Now an input goes unavailable -> no new setpoints, last state held.
    calls["number"].clear()
    set_inputs(hass, grid="unavailable", main_power=0, balcony_soc=40)
    await hass.async_block_till_done()
    await c.async_recalculate_now()
    await hass.async_block_till_done()

    assert c.mode == MODE_CHARGING  # unchanged
    assert c._last_sent_charge == sent_before
    assert len(calls["number"]) == 0  # nothing re-sent


async def test_disable_runs_deactivation(make_coordinator, hass):
    calls = _mock_all(hass)
    _prime_control_entities(hass, mode=MANUAL_VALUE, switch="on")
    set_inputs(hass, grid=600, main_power=0, balcony_soc=40)
    await hass.async_block_till_done()

    c = await make_coordinator()
    await c.async_recalculate_now()
    await hass.async_block_till_done()

    await c.async_disable()
    await hass.async_block_till_done()
    assert c.enabled is False
    # AC charging switched off as part of the safe deactivation.
    assert len(calls["switch_off"]) >= 1
    # While disabled, a control cycle does nothing.
    calls["number"].clear()
    await c.async_recalculate_now()
    await hass.async_block_till_done()
    assert len(calls["number"]) == 0


async def test_state_persists_across_restart(hass):
    """Mode + last sent setpoints + enabled survive a restart."""
    entry = MockConfigEntry(domain=DOMAIN, data=build_data())
    entry.add_to_hass(hass)

    c1 = BalconyBatteryCoordinator(hass, entry)
    await c1._async_restore()
    c1.enabled = False
    c1.mode = MODE_DISCHARGING
    c1._last_sent_charge = 0
    c1._last_sent_discharge = 350
    await c1._async_save()

    # Simulate a fresh start with the same entry/storage.
    c2 = BalconyBatteryCoordinator(hass, entry)
    await c2._async_restore()
    assert c2.enabled is False
    assert c2.mode == MODE_DISCHARGING
    assert c2._last_sent_discharge == 350
