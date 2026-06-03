"""Sensor platform for Balcony Battery Manager."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    KEY_MODE,
    KEY_SURPLUS,
    KEY_TARGET_CHARGE,
    KEY_TARGET_DISCHARGE,
    MODE_OPTIONS,
)
from .coordinator import BalconyBatteryCoordinator
from .entity import BalconyBatteryEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Balcony Battery Manager sensors."""
    coordinator: BalconyBatteryCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            BalconyModeSensor(coordinator),
            BalconyPowerSensor(coordinator, KEY_TARGET_CHARGE, "target_charge"),
            BalconyPowerSensor(coordinator, KEY_TARGET_DISCHARGE, "target_discharge"),
            BalconyPowerSensor(coordinator, KEY_SURPLUS, "surplus"),
        ]
    )


class BalconyModeSensor(BalconyBatteryEntity, SensorEntity):
    """Current state of the control state machine."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = MODE_OPTIONS

    def __init__(self, coordinator: BalconyBatteryCoordinator) -> None:
        super().__init__(coordinator, KEY_MODE)

    @property
    def native_value(self) -> str:
        return self.coordinator.data["mode"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.coordinator.data.get("attrs", {})


class BalconyPowerSensor(BalconyBatteryEntity, SensorEntity):
    """A power readout (target charge / discharge / computed surplus)."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(
        self, coordinator: BalconyBatteryCoordinator, key: str, data_key: str
    ) -> None:
        super().__init__(coordinator, key)
        self._data_key = data_key

    @property
    def native_value(self) -> float:
        return round(float(self.coordinator.data[self._data_key]))
