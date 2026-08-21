"""Diagnostic sensors exposing the controller state."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    KEY_DEMAND,
    KEY_MODE,
    KEY_SURPLUS,
    KEY_TARGET_POWER,
)
from .coordinator import BalconyBatteryCoordinator
from .entity import BalconyBatteryEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: BalconyBatteryCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            BalconyModeSensor(coordinator),
            BalconyPowerSensor(coordinator, KEY_TARGET_POWER),
            BalconyPowerSensor(coordinator, KEY_DEMAND),
            BalconyPowerSensor(coordinator, KEY_SURPLUS),
        ]
    )


class BalconyModeSensor(BalconyBatteryEntity, SensorEntity):
    """Current coordination mode (idle / discharge / charge / failsafe)."""

    def __init__(self, coordinator: BalconyBatteryCoordinator) -> None:
        super().__init__(coordinator, KEY_MODE)

    @property
    def native_value(self) -> str | None:
        return (self.coordinator.data or {}).get(KEY_MODE)

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data or {}
        return {
            "grid_flow": data.get("grid_flow"),
            "charge_release": data.get("charge_release"),
            "need_wh": data.get("need_wh"),
            "rest_pv_wh": data.get("rest_pv_wh"),
            "reason": data.get("reason"),
        }


class BalconyPowerSensor(BalconyBatteryEntity, SensorEntity):
    """A power-valued diagnostic sensor (target / corrected demand / surplus)."""

    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER

    @property
    def native_value(self) -> float | None:
        val = (self.coordinator.data or {}).get(self._key)
        return round(val) if isinstance(val, (int, float)) else None
