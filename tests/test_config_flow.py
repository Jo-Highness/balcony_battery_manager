"""Config / options flow tests for pre-fill and the unit selectors."""

from __future__ import annotations

from unittest.mock import patch

import voluptuous as vol
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.balcony_battery_manager.const import (
    CONF_GRID_POWER,
    CONF_GRID_POWER_UNIT,
    DEFAULT_POWER_UNIT,
    DOMAIN,
)
from tests.conftest import build_data, set_inputs

_FLOW = "custom_components.balcony_battery_manager.config_flow"


def _marker(schema, key):
    for marker in schema.schema:
        if marker.schema == key:
            return marker
    return None


def _suggested(schema, key):
    marker = _marker(schema, key)
    if marker is None or not marker.description:
        return None
    return marker.description.get("suggested_value")


def _default(schema, key):
    marker = _marker(schema, key)
    if marker is None or marker.default is vol.UNDEFINED:
        return None
    return marker.default() if callable(marker.default) else marker.default


async def test_initial_flow_prefills_and_unit_default(hass):
    async def _energy(_hass):
        return {CONF_GRID_POWER: "sensor.suggested_grid"}

    async def _anker(_hass):
        return {}

    with patch(f"{_FLOW}.suggested_inputs_from_energy", _energy), patch(
        f"{_FLOW}.suggested_from_anker", _anker
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )

    schema = result["data_schema"]
    assert _suggested(schema, CONF_GRID_POWER) == "sensor.suggested_grid"
    # The new unit selector defaults to "auto" so existing entries are unchanged.
    assert _default(schema, CONF_GRID_POWER_UNIT) == DEFAULT_POWER_UNIT


async def test_options_flow_does_not_prefill(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=build_data())
    entry.add_to_hass(hass)
    set_inputs(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    async def _energy(_hass):
        return {CONF_GRID_POWER: "sensor.should_not_appear"}

    # Even if the energy resolver would suggest something, the options flow must
    # never apply it — the user already has stored values.
    with patch(f"{_FLOW}.suggested_inputs_from_energy", _energy):
        result = await hass.config_entries.options.async_init(entry.entry_id)

    suggested = _suggested(result["data_schema"], CONF_GRID_POWER)
    assert suggested != "sensor.should_not_appear"
    assert suggested == build_data()[CONF_GRID_POWER]
