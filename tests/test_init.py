"""Setup / unload and service-registration tests."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.balcony_battery_manager.const import (
    DOMAIN,
    SERVICE_DISABLE,
    SERVICE_ENABLE,
    SERVICE_RECALCULATE_NOW,
)
from tests.conftest import build_data, set_inputs


async def test_setup_and_unload(hass):
    set_inputs(hass)
    await hass.async_block_till_done()

    entry = MockConfigEntry(domain=DOMAIN, data=build_data())
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Entities created.
    assert hass.states.get("switch.balcony_battery_manager_enabled") is not None
    assert hass.states.get("sensor.balcony_battery_manager_mode") is not None

    # Services registered.
    assert hass.services.has_service(DOMAIN, SERVICE_ENABLE)
    assert hass.services.has_service(DOMAIN, SERVICE_DISABLE)
    assert hass.services.has_service(DOMAIN, SERVICE_RECALCULATE_NOW)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not hass.services.has_service(DOMAIN, SERVICE_ENABLE)
