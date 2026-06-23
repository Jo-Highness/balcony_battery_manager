"""Config / options flow tests for pre-fill and the unit selectors."""

from __future__ import annotations

from unittest.mock import patch

import voluptuous as vol
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.balcony_battery_manager.const import (
    CONF_GRID_POWER,
    CONF_GRID_POWER_UNIT,
    CONF_MAIN_DISCHARGE_POSITIVE,
    CONF_MAIN_SOC,
    DEFAULT_POWER_UNIT,
    DOMAIN,
)
from tests.conftest import build_data, set_inputs

_FLOW = "custom_components.balcony_battery_manager.config_flow"


async def _no_suggestions(_hass):
    return {}


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
        f"{_FLOW}.suggested_from_e3dc", _no_suggestions
    ), patch(f"{_FLOW}.suggested_from_anker", _anker):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )

    schema = result["data_schema"]
    assert _suggested(schema, CONF_GRID_POWER) == "sensor.suggested_grid"
    # The new unit selector defaults to "auto" so existing entries are unchanged.
    assert _default(schema, CONF_GRID_POWER_UNIT) == DEFAULT_POWER_UNIT


def _is_optional(schema, key):
    marker = _marker(schema, key)
    return isinstance(marker, vol.Optional)


async def test_main_soc_is_optional(hass):
    # A roof system without a SOC sensor (E3DC via KNX) must still be able to
    # finish setup, so main_soc is Optional — not Required.
    with patch(f"{_FLOW}.suggested_inputs_from_energy", _no_suggestions), patch(
        f"{_FLOW}.suggested_from_e3dc", _no_suggestions
    ), patch(f"{_FLOW}.suggested_from_anker", _no_suggestions):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )

    assert _is_optional(result["data_schema"], CONF_MAIN_SOC)


async def test_sign_suggestion_flows_into_default(hass):
    # A vendor resolver (e.g. E3DC) may suggest the sign convention; it must
    # reach the form as the field default.
    async def _e3dc(_hass):
        return {CONF_MAIN_DISCHARGE_POSITIVE: False}

    with patch(f"{_FLOW}.suggested_inputs_from_energy", _no_suggestions), patch(
        f"{_FLOW}.suggested_from_e3dc", _e3dc
    ), patch(f"{_FLOW}.suggested_from_anker", _no_suggestions):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )

    assert _default(result["data_schema"], CONF_MAIN_DISCHARGE_POSITIVE) is False


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
