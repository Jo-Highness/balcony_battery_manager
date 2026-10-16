"""Setup / unload / migration tests for Balcony Battery Manager."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.balcony_battery_manager import const as C, logic
from custom_components.balcony_battery_manager.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import FULL_DATA


def _eid(hass: HomeAssistant, entry, platform: str, key: str) -> str:
    ent_reg = er.async_get(hass)
    eid = ent_reg.async_get_entity_id(platform, C.DOMAIN, f"{entry.entry_id}_{key}")
    assert eid, f"entity {platform}/{key} not registered"
    return eid


async def test_setup_creates_entities(hass: HomeAssistant, config_entry) -> None:
    """Setup registers the diagnostic sensors + the master switch.

    No input sensors exist in the test hass, so the coordinator takes its
    fail-safe path (0 W) on the first cycle — setup must still succeed.
    """
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED

    mode = _eid(hass, config_entry, "sensor", C.KEY_MODE)
    _eid(hass, config_entry, "sensor", C.KEY_TARGET_POWER)
    _eid(hass, config_entry, "sensor", C.KEY_DEMAND)
    _eid(hass, config_entry, "sensor", C.KEY_SURPLUS)
    switch = _eid(hass, config_entry, "switch", C.KEY_ENABLED)

    assert hass.states.get(mode).state == "failsafe"
    assert hass.states.get(switch).state == "on"

    coordinator = config_entry.runtime_data
    assert coordinator.last_update_success is True
    assert coordinator.data[C.KEY_ENABLED] is True


async def test_unload(hass: HomeAssistant, config_entry) -> None:
    """The entry unloads cleanly and drops its coordinator."""
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_disable_service_sets_disabled_mode(hass: HomeAssistant, config_entry) -> None:
    """The disable service switches the master switch off and the mode to disabled."""
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(C.DOMAIN, C.SERVICE_DISABLE, {}, blocking=True)
    await hass.async_block_till_done()

    coordinator = config_entry.runtime_data
    assert coordinator.data[C.KEY_ENABLED] is False
    assert coordinator.data[C.KEY_MODE] == "disabled"


async def test_migration_rejects_v1(hass: HomeAssistant) -> None:
    """A pre-v2 (Solarbank 3) entry is rejected — no automatic migration."""
    old = MockConfigEntry(domain=C.DOMAIN, title="old", version=1, data=dict(FULL_DATA))
    old.add_to_hass(hass)
    await hass.config_entries.async_setup(old.entry_id)
    await hass.async_block_till_done()
    assert old.state is ConfigEntryState.MIGRATION_ERROR


async def test_master_switch_off_survives_reload(hass: HomeAssistant, config_entry) -> None:
    """A deliberate 'off' is persisted (NFR-4/A-5) and not silently re-enabled."""
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(C.DOMAIN, C.SERVICE_DISABLE, {}, blocking=True)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    coordinator = config_entry.runtime_data
    assert coordinator.data[C.KEY_ENABLED] is False
    assert coordinator.data[C.KEY_MODE] == "disabled"
    switch = _eid(hass, config_entry, "switch", C.KEY_ENABLED)
    assert hass.states.get(switch).state == "off"

    # ... and switching it back on is persisted as well.
    await hass.services.async_call(C.DOMAIN, C.SERVICE_ENABLE, {}, blocking=True)
    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.runtime_data.data[C.KEY_ENABLED] is True


async def test_decide_receives_local_time(hass: HomeAssistant, config_entry) -> None:
    """The afternoon cap hour is local wall-clock time -> decide() gets local `now`."""
    await hass.config.async_set_time_zone("Europe/Berlin")
    for key, value in (
        (C.CONF_P_BATT_DRAW, "100"),
        (C.CONF_P_ANKER_OUT, "0"),
        (C.CONF_P_GRID, "0"),
        (C.CONF_SOC_ANKER, "50"),
        (C.CONF_P_ANKER_PV, "300"),
    ):
        hass.states.async_set(FULL_DATA[key], value)

    seen: list = []
    real_decide = logic.decide

    def _spy(*args, **kwargs):
        seen.append(kwargs["now"])
        return real_decide(*args, **kwargs)

    config_entry.add_to_hass(hass)
    with patch.object(logic, "decide", _spy):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert seen, "decide() was not called"
    now = seen[-1]
    assert now.utcoffset() == dt_util.now().utcoffset()
    assert now.hour == dt_util.now().hour


async def test_migration_v21_moves_data_to_options(hass: HomeAssistant) -> None:
    """v2.1 entries (settings in data, partial options) are merged into options."""
    old = MockConfigEntry(
        domain=C.DOMAIN,
        version=2,
        minor_version=1,
        data={**FULL_DATA, C.CONF_MAIN_SOC: "sensor.main_soc"},
        options={C.CONF_INTERVAL: 60.0},
    )
    old.add_to_hass(hass)
    await hass.config_entries.async_setup(old.entry_id)
    await hass.async_block_till_done()
    assert old.state is ConfigEntryState.LOADED
    assert old.minor_version == C.CONFIG_MINOR_VERSION
    assert old.data == {}
    assert old.options[C.CONF_INTERVAL] == 60.0
    assert old.options[C.CONF_MAIN_SOC] == "sensor.main_soc"
    assert old.unique_id == FULL_DATA[C.CONF_TARGET_POWER_NUMBER]


async def test_services_target_entry(hass: HomeAssistant, config_entry, actuators) -> None:
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            C.DOMAIN, C.SERVICE_DISABLE, {C.ATTR_CONFIG_ENTRY_ID: "nope"}, blocking=True
        )
    await hass.services.async_call(
        C.DOMAIN,
        C.SERVICE_DISABLE,
        {C.ATTR_CONFIG_ENTRY_ID: config_entry.entry_id},
        blocking=True,
    )
    assert config_entry.runtime_data.enabled is False
    assert actuators.calls[-1] == ("number", 0)
    await hass.services.async_call(
        C.DOMAIN,
        C.SERVICE_RECALCULATE_NOW,
        {C.ATTR_CONFIG_ENTRY_ID: config_entry.entry_id},
        blocking=True,
    )


async def test_switch_turns_control_off(hass: HomeAssistant, config_entry, actuators) -> None:
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    switch = _eid(hass, config_entry, "switch", C.KEY_ENABLED)
    ent = er.async_get(hass).async_get(switch)
    assert ent.entity_category is None  # a primary control, not a config entity
    await hass.services.async_call("switch", "turn_off", {"entity_id": switch}, blocking=True)
    assert hass.states.get(switch).state == "off"
    mode = _eid(hass, config_entry, "sensor", C.KEY_MODE)
    assert hass.states.get(mode).state == C.MODE_DISABLED
    await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(switch).state == "on"


async def test_sensor_classes(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    mode = hass.states.get(_eid(hass, config_entry, "sensor", C.KEY_MODE))
    assert mode.attributes["device_class"] == "enum"
    assert mode.attributes["options"] == C.MODES
    power = hass.states.get(_eid(hass, config_entry, "sensor", C.KEY_TARGET_POWER))
    assert power.attributes["state_class"] == "measurement"
    assert power.attributes["device_class"] == "power"


async def test_unload_sets_zero(hass: HomeAssistant, config_entry, actuators) -> None:
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    actuators.calls.clear()
    config_entry.runtime_data._last_written = ("discharge", 300.0)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert actuators.calls == [("number", 0)]


async def test_diagnostics(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    diag = await async_get_config_entry_diagnostics(hass, config_entry)
    assert diag["entry"]["options"][C.CONF_P_GRID] == FULL_DATA[C.CONF_P_GRID]
    assert diag["data"][C.KEY_MODE] == "failsafe"
    assert "controller" in diag["state"]
