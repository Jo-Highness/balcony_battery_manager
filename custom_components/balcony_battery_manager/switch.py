"""Switch platform for Balcony Battery Manager (the master switch)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import KEY_ENABLED
from .coordinator import BalconyBatteryConfigEntry, BalconyBatteryCoordinator
from .entity import BalconyBatteryEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BalconyBatteryConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Balcony Battery Manager master switch."""
    async_add_entities([BalconyMasterSwitch(entry.runtime_data)])


class BalconyMasterSwitch(BalconyBatteryEntity, SwitchEntity):
    """Master switch enabling/disabling the control loop (a primary control)."""

    def __init__(self, coordinator: BalconyBatteryCoordinator) -> None:
        super().__init__(coordinator, KEY_ENABLED)

    @property
    def is_on(self) -> bool:
        return self.coordinator.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_enable()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_disable()
