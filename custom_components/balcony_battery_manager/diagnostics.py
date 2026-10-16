"""Diagnostics for Balcony Battery Manager.

Contains only entity ids, tunables and controller state - no credentials or
tokens exist in this integration.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import BalconyBatteryConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BalconyBatteryConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": {
            "version": f"{entry.version}.{entry.minor_version}",
            "options": dict(entry.options),
        },
        "data": coordinator.data,
        "state": coordinator.diagnostics(),
    }
