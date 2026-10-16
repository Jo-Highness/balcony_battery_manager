"""Config- and options-flow tests for Balcony Battery Manager."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from custom_components.balcony_battery_manager import const as C

from .conftest import FULL_DATA, Actuators, nest


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
    with patch("custom_components.balcony_battery_manager.prefill.suggest", return_value={}):
        result = await hass.config_entries.flow.async_init(
            C.DOMAIN, context={"source": SOURCE_USER}
        )
    assert result["type"] is FlowResultType.FORM
    for section_marker, section in result["data_schema"].schema.items():
        assert getattr(section_marker, "description", None) is not vol.UNDEFINED
        for marker in section.schema.schema:
            assert getattr(marker, "description", None) is not vol.UNDEFINED


async def test_flow_happy_path(hass: HomeAssistant) -> None:
    """Submitting a full, valid parameter set creates the entry."""
    result = await hass.config_entries.flow.async_init(C.DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], nest(FULL_DATA))

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Balcony Battery Manager"
    assert result["data"] == {}
    assert result["options"][C.CONF_P_ANKER_OUT] == "sensor.anker_out"
    assert result["options"][C.CONF_INTERVAL] == 30.0
    assert result["result"].unique_id == FULL_DATA[C.CONF_TARGET_POWER_NUMBER]


async def test_options_flow_update_interval(hass: HomeAssistant, config_entry) -> None:
    """The control interval can be changed through the options flow."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    new_opts = dict(FULL_DATA)
    new_opts[C.CONF_INTERVAL] = 60.0
    result = await hass.config_entries.options.async_configure(result["flow_id"], nest(new_opts))

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options[C.CONF_INTERVAL] == 60.0


async def _submit(hass: HomeAssistant, flat: dict):
    result = await hass.config_entries.flow.async_init(C.DOMAIN, context={"source": SOURCE_USER})
    return await hass.config_entries.flow.async_configure(result["flow_id"], nest(flat))


async def test_form_uses_sections(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(C.DOMAIN, context={"source": SOURCE_USER})
    keys = {str(k) for k in result["data_schema"].schema}
    assert keys == {"measurements", "actuators", "discharge", "charging", "grid_support", "general"}


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({C.CONF_DISCHARGE_TH1: 1600.0, C.CONF_DISCHARGE_TH2: 800.0}, "threshold_order"),
        ({C.CONF_DISCHARGE_STAGE1: 900.0}, "stage_order"),
        ({C.CONF_GRID_FLOW_CHARGE: "discharge"}, "grid_flow_options_equal"),
        ({C.CONF_GRID_FLOW_DISCHARGE: "feed_in"}, "grid_flow_option_missing"),
        ({C.CONF_RESTORE_MODE: "self_consumption"}, "mode_select_missing"),
        ({C.CONF_MODE_SELECT: "select.anker_mode"}, "mode_option_required"),
        (
            {C.CONF_MODE_SELECT: "select.anker_mode", C.CONF_RESTORE_MODE: "nope"},
            "mode_option_missing",
        ),
    ],
)
async def test_validation_errors(hass: HomeAssistant, actuators, change, error) -> None:
    result = await _submit(hass, {**FULL_DATA, **change})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_validation_units(hass: HomeAssistant, actuators) -> None:
    hass.states.async_set(FULL_DATA[C.CONF_P_GRID], "1", {"unit_of_measurement": "A"})
    result = await _submit(hass, FULL_DATA)
    assert result["errors"] == {"base": "power_unit_invalid"}

    hass.states.async_set(FULL_DATA[C.CONF_P_GRID], "1", {"unit_of_measurement": "kW"})
    hass.states.async_set(FULL_DATA[C.CONF_SOC_ANKER], "1", {"unit_of_measurement": "kWh"})
    result = await _submit(hass, FULL_DATA)
    assert result["errors"] == {"base": "soc_unit_invalid"}

    hass.states.async_set(FULL_DATA[C.CONF_SOC_ANKER], "1", {"unit_of_measurement": "%"})
    hass.states.async_set(Actuators.NUMBER, "0", {"unit_of_measurement": "A"})
    result = await _submit(hass, FULL_DATA)
    assert result["errors"] == {"base": "number_unit_invalid"}


async def test_valid_mode_options_accepted(hass: HomeAssistant, actuators) -> None:
    result = await _submit(
        hass,
        {
            **FULL_DATA,
            C.CONF_MODE_SELECT: "select.anker_mode",
            C.CONF_CONTROL_MODE: "third_party",
            C.CONF_RESTORE_MODE: "self_consumption",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][C.CONF_RESTORE_MODE] == "self_consumption"


async def test_second_entry_same_actuator_aborts(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await _submit(hass, FULL_DATA)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_second_entry_same_select_aborts(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await _submit(hass, {**FULL_DATA, C.CONF_TARGET_POWER_NUMBER: "number.other"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_clears_optional_field(hass: HomeAssistant) -> None:
    """Removing the optional main-battery SoC in the options really removes it."""
    entry = MockConfigEntry(
        domain=C.DOMAIN,
        version=C.CONFIG_VERSION,
        minor_version=C.CONFIG_MINOR_VERSION,
        data={},
        options={**FULL_DATA, C.CONF_MAIN_SOC: "sensor.main_soc"},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], nest(FULL_DATA))
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert C.CONF_MAIN_SOC not in entry.options


async def test_options_flow_validation_and_unique_id(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    bad = {**FULL_DATA, C.CONF_DISCHARGE_TH1: 2000.0}
    result = await hass.config_entries.options.async_configure(result["flow_id"], nest(bad))
    assert result["errors"] == {"base": "threshold_order"}

    new = {**FULL_DATA, C.CONF_TARGET_POWER_NUMBER: "number.new_target"}
    result = await hass.config_entries.options.async_configure(result["flow_id"], nest(new))
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.unique_id == "number.new_target"


async def test_options_flow_rejects_actuator_of_other_entry(
    hass: HomeAssistant, config_entry
) -> None:
    config_entry.add_to_hass(hass)
    other = MockConfigEntry(
        domain=C.DOMAIN,
        version=C.CONFIG_VERSION,
        minor_version=C.CONFIG_MINOR_VERSION,
        data={},
        options={
            **FULL_DATA,
            C.CONF_TARGET_POWER_NUMBER: "number.b",
            C.CONF_GRID_FLOW_SELECT: "select.b",
        },
    )
    other.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(other.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], nest({**FULL_DATA, C.CONF_GRID_FLOW_SELECT: "select.b"})
    )
    assert result["errors"] == {"base": "actuator_in_use"}
