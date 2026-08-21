"""Config- and options-flow tests for Balcony Battery Manager."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import voluptuous as vol

from custom_components.balcony_battery_manager import const as C

from .conftest import FULL_DATA


async def test_form_shown(hass: HomeAssistant) -> None:
    """The initial step shows the parameter form."""
    result = await hass.config_entries.flow.async_init(C.DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_form_serialisable_without_prefill(hass: HomeAssistant) -> None:
    """With no prefill matches the form schema must stay JSON-serialisable.

    A leftover ``vol.UNDEFINED`` description leaks into the schema and makes the
    flow crash with HTTP 500 in the frontend on any install whose entities are
    not named like the author's. Guard against that regression.
    """
    with patch(
        "custom_components.balcony_battery_manager.prefill.suggest", return_value={}
    ):
        result = await hass.config_entries.flow.async_init(
            C.DOMAIN, context={"source": SOURCE_USER}
        )
    assert result["type"] is FlowResultType.FORM
    for marker in result["data_schema"].schema:
        assert getattr(marker, "description", None) is not vol.UNDEFINED


async def test_flow_happy_path(hass: HomeAssistant) -> None:
    """Submitting a full, valid parameter set creates the entry."""
    result = await hass.config_entries.flow.async_init(C.DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(FULL_DATA))

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Balcony Battery Manager"
    assert result["data"][C.CONF_P_ANKER_OUT] == "sensor.anker_out"
    assert result["data"][C.CONF_INTERVAL] == 30.0


async def test_options_flow_update_interval(hass: HomeAssistant, config_entry) -> None:
    """The control interval can be changed through the options flow."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    new_opts = dict(FULL_DATA)
    new_opts[C.CONF_INTERVAL] = 60.0
    result = await hass.config_entries.options.async_configure(result["flow_id"], new_opts)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options[C.CONF_INTERVAL] == 60.0
