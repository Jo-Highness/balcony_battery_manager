"""Logic tests for the Balcony Battery Manager coordinator."""

from __future__ import annotations

import pytest

from custom_components.balcony_battery_manager.const import (
    CONF_GRID_SUPPORT_ENABLED,
    MODE_CHARGING,
    MODE_DISCHARGING,
    MODE_IDLE,
    REASON_GRID_SUPPORT,
    REASON_RELIEF,
)
from custom_components.balcony_battery_manager.coordinator import Inputs


def _inp(**kw) -> Inputs:
    base = dict(
        grid_export=0.0,
        main_discharge=0.0,
        main_soc=50.0,
        balcony_soc=50.0,
        balcony_power=0.0,
    )
    base.update(kw)
    return Inputs(**base)


async def test_charge_surplus_reconstruction_and_headroom(make_coordinator):
    """S = measured export + last sent charge; target = S - headroom."""
    c = await make_coordinator()
    c.mode = MODE_IDLE
    c._last_sent_charge = 300  # we are already drawing 300 W
    # Measured export only 500 W because our charging hides 300 W of it.
    decision = c._evaluate(_inp(grid_export=500, balcony_soc=50))
    assert decision.mode == MODE_CHARGING
    assert decision.surplus == 800  # 500 + 300
    assert decision.target_charge == 600  # 800 - 200 headroom


async def test_charge_clamped_to_max(make_coordinator):
    c = await make_coordinator(max_charge_power=1100)
    c._last_sent_charge = 0
    decision = c._evaluate(_inp(grid_export=5000, balcony_soc=20))
    assert decision.target_charge == 1100


async def test_stop_charging_at_soc_100(make_coordinator):
    """At 100 % SOC charging must stop even with surplus present."""
    c = await make_coordinator()
    c._last_sent_charge = 300
    decision = c._evaluate(_inp(grid_export=500, balcony_soc=100))
    assert decision.mode == MODE_IDLE
    assert decision.target_charge == 0


async def test_discharge_activation_above_threshold(make_coordinator):
    """Main-battery discharge > 400 W activates the balcony discharge."""
    c = await make_coordinator()
    c.mode = MODE_IDLE
    c._last_sent_discharge = 0
    decision = c._evaluate(_inp(main_discharge=450))
    assert decision.mode == MODE_DISCHARGING
    assert decision.target_discharge == 225  # 450 * 0.5


async def test_discharge_not_activated_in_deadzone(make_coordinator):
    """Between off (100) and on (400) thresholds, idle stays idle."""
    c = await make_coordinator()
    c.mode = MODE_IDLE
    decision = c._evaluate(_inp(main_discharge=150))
    assert decision.mode == MODE_IDLE


async def test_discharge_steady_state_50_50(make_coordinator):
    """200 W main + 200 W balcony already sent -> stable 200 W target."""
    c = await make_coordinator()
    c.mode = MODE_DISCHARGING
    c._last_sent_discharge = 200
    decision = c._evaluate(_inp(main_discharge=200))
    assert decision.mode == MODE_DISCHARGING
    assert decision.target_discharge == 200  # (200 + 200) * 0.5


async def test_discharge_hysteresis_stays_active(make_coordinator):
    """While discharging, stays active down to the off threshold."""
    c = await make_coordinator()
    c.mode = MODE_DISCHARGING
    c._last_sent_discharge = 200
    decision = c._evaluate(_inp(main_discharge=150))  # 150 >= off(100)
    assert decision.mode == MODE_DISCHARGING


async def test_discharge_deactivation_below_threshold(make_coordinator):
    """Below the off threshold (100 W) discharge stops -> IDLE."""
    c = await make_coordinator()
    c.mode = MODE_DISCHARGING
    c._last_sent_discharge = 200
    decision = c._evaluate(_inp(main_discharge=90))
    assert decision.mode == MODE_IDLE
    assert decision.target_discharge == 0


async def test_discharge_clamped_to_max_house_feed(make_coordinator):
    c = await make_coordinator(max_house_feed=800)
    c.mode = MODE_DISCHARGING
    c._last_sent_discharge = 800
    decision = c._evaluate(_inp(main_discharge=3000))
    assert decision.target_discharge == 800


async def test_discharge_priority_over_charge(make_coordinator):
    """Discharge wins arbitration even if a surplus also looks present."""
    c = await make_coordinator()
    c.mode = MODE_IDLE
    decision = c._evaluate(_inp(grid_export=500, main_discharge=450))
    assert decision.mode == MODE_DISCHARGING


async def test_grid_support_activates_when_main_empty(make_coordinator):
    """Main battery empty + grid import + balcony has charge -> discharge to cover import."""
    c = await make_coordinator()
    c.mode = MODE_IDLE
    c._last_sent_discharge = 0
    # Importing 300 W from grid (grid_export = -300), main empty (5% <= 10%).
    decision = c._evaluate(
        _inp(grid_export=-300, main_discharge=0, main_soc=5, balcony_soc=80)
    )
    assert decision.mode == MODE_DISCHARGING
    assert decision.reason == REASON_GRID_SUPPORT
    assert decision.target_discharge == 300  # cover the whole import


async def test_grid_support_reconstructs_hidden_import(make_coordinator):
    """Steady state: our 300 W output hides the import, grid now balanced -> stay at 300."""
    c = await make_coordinator()
    c.mode = MODE_DISCHARGING
    c._last_sent_discharge = 300
    decision = c._evaluate(
        _inp(grid_export=0, main_discharge=0, main_soc=5, balcony_soc=70)
    )
    assert decision.mode == MODE_DISCHARGING
    assert decision.target_discharge == 300  # 300 - 0 = 300


async def test_grid_support_not_active_when_main_has_charge(make_coordinator):
    """If the main battery is NOT empty, the balcony must not drain for grid import."""
    c = await make_coordinator()
    c.mode = MODE_IDLE
    decision = c._evaluate(
        _inp(grid_export=-300, main_discharge=0, main_soc=50, balcony_soc=80)
    )
    assert decision.mode == MODE_IDLE


async def test_grid_support_respects_disable_flag(make_coordinator):
    c = await make_coordinator(**{CONF_GRID_SUPPORT_ENABLED: False})
    c.mode = MODE_IDLE
    decision = c._evaluate(
        _inp(grid_export=-300, main_discharge=0, main_soc=5, balcony_soc=80)
    )
    assert decision.mode == MODE_IDLE


async def test_grid_support_needs_balcony_charge(make_coordinator):
    c = await make_coordinator()
    c.mode = MODE_IDLE
    decision = c._evaluate(
        _inp(grid_export=-300, main_discharge=0, main_soc=5, balcony_soc=0)
    )
    assert decision.mode == MODE_IDLE


async def test_grid_support_clamped_to_max_house_feed(make_coordinator):
    c = await make_coordinator(max_house_feed=800)
    c.mode = MODE_IDLE
    decision = c._evaluate(
        _inp(grid_export=-3000, main_discharge=0, main_soc=2, balcony_soc=90)
    )
    assert decision.target_discharge == 800


async def test_relief_still_wins_when_main_discharging(make_coordinator):
    """When the main battery is actively discharging, relief logic applies (reason=relief)."""
    c = await make_coordinator()
    c.mode = MODE_IDLE
    c._last_sent_discharge = 0
    decision = c._evaluate(
        _inp(grid_export=-20, main_discharge=450, main_soc=60, balcony_soc=80)
    )
    assert decision.mode == MODE_DISCHARGING
    assert decision.reason == REASON_RELIEF
    assert decision.target_discharge == 225


def _exceeds(c, new, last):
    return c._exceeds_deadband(new, last)


async def test_deadband(make_coordinator):
    c = await make_coordinator(deadband=25)
    assert _exceeds(c, 210, 200) is False  # 10 W change, ignored
    assert _exceeds(c, 225, 200) is False  # exactly 25, not > 25
    assert _exceeds(c, 230, 200) is True  # 30 W change, send


async def test_read_inputs_failsafe_on_unavailable(make_coordinator, hass):
    from tests.conftest import set_inputs

    c = await make_coordinator()
    set_inputs(hass, grid="unavailable", main_power=0, balcony_soc=50)
    await hass.async_block_till_done()
    assert c._read_inputs() is None


async def test_read_inputs_rejects_bad_soc(make_coordinator, hass):
    from tests.conftest import set_inputs

    c = await make_coordinator()
    set_inputs(hass, grid=0, main_power=0, balcony_soc=-5)
    await hass.async_block_till_done()
    assert c._read_inputs() is None


async def test_read_inputs_sign_inversion(make_coordinator, hass):
    """When export_positive is off, a negative raw value means export."""
    from custom_components.balcony_battery_manager.const import (
        CONF_GRID_EXPORT_POSITIVE,
    )
    from tests.conftest import set_inputs

    c = await make_coordinator(**{CONF_GRID_EXPORT_POSITIVE: False})
    set_inputs(hass, grid=-700, main_power=0, balcony_soc=50)
    await hass.async_block_till_done()
    inp = c._read_inputs()
    assert inp is not None
    assert inp.grid_export == 700
