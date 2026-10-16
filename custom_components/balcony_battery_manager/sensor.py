"""Sensors exposing the controller state."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import KEY_DEMAND, KEY_MODE, KEY_SURPLUS, KEY_TARGET_POWER, MODES
from .coordinator import BalconyBatteryConfigEntry, BalconyBatteryCoordinator
from .entity import BalconyBatteryEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BalconyBatteryConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            BalconyModeSensor(coordinator),
            BalconyPowerSensor(coordinator, KEY_TARGET_POWER),
            BalconyPowerSensor(coordinator, KEY_DEMAND),
            BalconyPowerSensor(coordinator, KEY_SURPLUS),
        ]
    )


class BalconyModeSensor(BalconyBatteryEntity, SensorEntity):
    """Current coordination mode (see const.MODES)."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = MODES

    def __init__(self, coordinator: BalconyBatteryCoordinator) -> None:
        super().__init__(coordinator, KEY_MODE)

    @property
    def native_value(self) -> str | None:
        return (self.coordinator.data or {}).get(KEY_MODE)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        return {
            "grid_flow": data.get("grid_flow"),
            "applied_power": data.get("applied_power"),
            "charge_release": data.get("charge_release"),
            "need_wh": data.get("need_wh"),
            "rest_pv_wh": data.get("rest_pv_wh"),
            "reason": data.get("reason"),
        }


class BalconyPowerSensor(BalconyBatteryEntity, SensorEntity):
    """A power-valued sensor (target / corrected demand / surplus)."""

    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        val = (self.coordinator.data or {}).get(self._key)
        return round(val) if isinstance(val, (int, float)) else None
