"""The Balcony Battery Manager integration (v2, Anker SOLIX Solarbank 4)."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import CoreState, HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .const import (
    ATTR_CONFIG_ENTRY_ID,
    CONF_GRID_FLOW_SELECT,
    CONF_TARGET_POWER_NUMBER,
    CONFIG_MINOR_VERSION,
    CONFIG_VERSION,
    DOMAIN,
    SERVICE_DISABLE,
    SERVICE_ENABLE,
    SERVICE_RECALCULATE_NOW,
)
from .coordinator import STORAGE_VERSION, BalconyBatteryConfigEntry, BalconyBatteryCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.SWITCH]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_SCHEMA = vol.Schema({vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string})


async def async_setup(hass: HomeAssistant, _config: ConfigType) -> bool:
    """Register the integration's actions once."""

    def _targets(call: ServiceCall) -> list[BalconyBatteryCoordinator]:
        entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)
        if entry_id:
            entry = hass.config_entries.async_get_entry(entry_id)
            loaded = entry is not None and entry.state is ConfigEntryState.LOADED
            if entry is None or entry.domain != DOMAIN or not loaded:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="entry_not_loaded",
                    translation_placeholders={"entry_id": entry_id},
                )
            return [entry.runtime_data]
        return [
            e.runtime_data
            for e in hass.config_entries.async_entries(DOMAIN)
            if e.state is ConfigEntryState.LOADED
            and isinstance(getattr(e, "runtime_data", None), BalconyBatteryCoordinator)
        ]

    async def _handle_enable(call: ServiceCall) -> None:
        for coordinator in _targets(call):
            await coordinator.async_enable()

    async def _handle_disable(call: ServiceCall) -> None:
        for coordinator in _targets(call):
            await coordinator.async_disable()

    async def _handle_recalculate(call: ServiceCall) -> None:
        for coordinator in _targets(call):
            await coordinator.async_recalculate_now()

    hass.services.async_register(DOMAIN, SERVICE_ENABLE, _handle_enable, SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DISABLE, _handle_disable, SERVICE_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_RECALCULATE_NOW, _handle_recalculate, SERVICE_SCHEMA
    )
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entries.

    * v1 (Solarbank 3) -> rejected: the v2 rewrite targets the Solarbank 4 with
      an incompatible actuator model; the user has to remove and re-add it.
    * v2.1 -> v2.2: move every setting into ``entry.options`` (``data`` becomes
      empty) so optional fields can be cleared in the options flow, and set the
      unique_id to the target-power number entity.
    """
    if entry.version < CONFIG_VERSION:
        _LOGGER.error(
            "Balcony Battery Manager v2 is a BREAKING CHANGE (Solarbank 3 -> 4). "
            "The old config entry (v%s) cannot be migrated automatically. Please "
            "remove this integration and add it again to reconfigure it for the "
            "Solarbank 4.",
            entry.version,
        )
        return False
    if entry.version > CONFIG_VERSION:
        return False  # downgrade from a future major version

    if entry.minor_version < 2:
        merged = {**entry.data, **entry.options}
        unique_id = entry.unique_id
        number = merged.get(CONF_TARGET_POWER_NUMBER)
        if unique_id is None and number:
            taken = any(
                e.unique_id == number
                for e in hass.config_entries.async_entries(DOMAIN)
                if e.entry_id != entry.entry_id
            )
            unique_id = None if taken else number
        hass.config_entries.async_update_entry(
            entry,
            data={},
            options=merged,
            unique_id=unique_id,
            minor_version=CONFIG_MINOR_VERSION,
        )
        _LOGGER.debug("Migrated %s to version 2.%s", entry.entry_id, CONFIG_MINOR_VERSION)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: BalconyBatteryConfigEntry) -> bool:
    """Set up Balcony Battery Manager from a config entry."""
    _warn_shared_actuators(hass, entry)
    coordinator = BalconyBatteryCoordinator(hass, entry)
    await coordinator.async_setup()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BalconyBatteryConfigEntry) -> bool:
    """Unload a config entry; leave the Solarbank at 0 W (except on shutdown)."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and hass.state is CoreState.running:
        await entry.runtime_data.async_release_on_unload()
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Drop the persisted master-switch state when the entry is deleted."""
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _warn_shared_actuators(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Log if another entry already drives the same actuator entities."""
    mine = {**entry.data, **entry.options}
    for other in hass.config_entries.async_entries(DOMAIN):
        if other.entry_id == entry.entry_id:
            continue
        theirs = {**other.data, **other.options}
        for key in (CONF_TARGET_POWER_NUMBER, CONF_GRID_FLOW_SELECT):
            if mine.get(key) and mine.get(key) == theirs.get(key):
                _LOGGER.warning(
                    "%s is also controlled by config entry %s; two controllers "
                    "on one Solarbank will fight each other",
                    mine[key],
                    other.title,
                )
