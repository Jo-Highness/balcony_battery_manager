"""The Balcony Battery Manager integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .const import (
    DOMAIN,
    SERVICE_DISABLE,
    SERVICE_ENABLE,
    SERVICE_RECALCULATE_NOW,
)
from .coordinator import BalconyBatteryCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "switch"]


def _coordinators(hass: HomeAssistant) -> list[BalconyBatteryCoordinator]:
    return [
        c
        for c in hass.data.get(DOMAIN, {}).values()
        if isinstance(c, BalconyBatteryCoordinator)
    ]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Balcony Battery Manager from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    coordinator = BalconyBatteryCoordinator(hass, entry)
    await coordinator.async_setup()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: BalconyBatteryCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    if not hass.data.get(DOMAIN):
        for service in (SERVICE_ENABLE, SERVICE_DISABLE, SERVICE_RECALCULATE_NOW):
            hass.services.async_remove(DOMAIN, service)

    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_ENABLE):
        return

    async def _handle_enable(_call: ServiceCall) -> None:
        for coordinator in _coordinators(hass):
            await coordinator.async_enable()

    async def _handle_disable(_call: ServiceCall) -> None:
        for coordinator in _coordinators(hass):
            await coordinator.async_disable()

    async def _handle_recalculate(_call: ServiceCall) -> None:
        for coordinator in _coordinators(hass):
            await coordinator.async_recalculate_now()

    hass.services.async_register(DOMAIN, SERVICE_ENABLE, _handle_enable)
    hass.services.async_register(DOMAIN, SERVICE_DISABLE, _handle_disable)
    hass.services.async_register(DOMAIN, SERVICE_RECALCULATE_NOW, _handle_recalculate)
