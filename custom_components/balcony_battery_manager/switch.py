"""Switch platform for Balcony Battery Manager (the master switch)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, KEY_ENABLED
from .coordinator import BalconyBatteryCoordinator
from .entity import BalconyBatteryEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Balcony Battery Manager master switch."""
    coordinator: BalconyBatteryCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BalconyMasterSwitch(coordinator)])


class BalconyMasterSwitch(BalconyBatteryEntity, SwitchEntity):
    """Master switch enabling/disabling the control loop."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: BalconyBatteryCoordinator) -> None:
        super().__init__(coordinator, KEY_ENABLED)

    @property
    def is_on(self) -> bool:
        return self.coordinator.data["enabled"]

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_enable()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_disable()
