"""Base entity for Balcony Battery Manager."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BalconyBatteryCoordinator


class BalconyBatteryEntity(CoordinatorEntity[BalconyBatteryCoordinator]):
    """Base class for Balcony Battery Manager entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BalconyBatteryCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name="Balcony Battery Manager",
            manufacturer="Balcony Battery Manager",
            model="Anker Solix balcony battery controller",
        )
