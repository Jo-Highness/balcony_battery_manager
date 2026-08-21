"""Setup / unload / migration tests for Balcony Battery Manager."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.balcony_battery_manager import const as C

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

    coordinator = hass.data[C.DOMAIN][config_entry.entry_id]
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
    assert config_entry.entry_id not in hass.data.get(C.DOMAIN, {})


async def test_disable_service_sets_disabled_mode(hass: HomeAssistant, config_entry) -> None:
    """The disable service switches the master switch off and the mode to disabled."""
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(C.DOMAIN, C.SERVICE_DISABLE, {}, blocking=True)
    await hass.async_block_till_done()

    coordinator = hass.data[C.DOMAIN][config_entry.entry_id]
    assert coordinator.data[C.KEY_ENABLED] is False
    assert coordinator.data[C.KEY_MODE] == "disabled"


async def test_migration_rejects_v1(hass: HomeAssistant) -> None:
    """A pre-v2 (Solarbank 3) entry is rejected — no automatic migration."""
    old = MockConfigEntry(domain=C.DOMAIN, title="old", version=1, data=dict(FULL_DATA))
    old.add_to_hass(hass)
    await hass.config_entries.async_setup(old.entry_id)
    await hass.async_block_till_done()
    assert old.state is ConfigEntryState.MIGRATION_ERROR
