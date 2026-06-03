"""Config & options flow for Balcony Battery Manager."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_AC_CHARGE_NUMBER,
    CONF_AC_CHARGE_SWITCH,
    CONF_BALCONY_DISCHARGE_POSITIVE,
    CONF_BALCONY_POWER,
    CONF_BALCONY_SOC,
    CONF_CHARGE_HEADROOM,
    CONF_DEACTIVATION_BEHAVIOR,
    CONF_DEACTIVATION_MODE_VALUE,
    CONF_DEADBAND,
    CONF_DISCHARGE_NUMBER,
    CONF_DISCHARGE_OFF_THRESHOLD,
    CONF_DISCHARGE_ON_THRESHOLD,
    CONF_DISCHARGE_SHARE,
    CONF_FAILSAFE_AFTER,
    CONF_GRID_EXPORT_POSITIVE,
    CONF_GRID_IMPORT_OFF_THRESHOLD,
    CONF_GRID_IMPORT_ON_THRESHOLD,
    CONF_GRID_POWER,
    CONF_GRID_SUPPORT_ENABLED,
    CONF_INTERVAL,
    CONF_MAIN_EMPTY_SOC,
    CONF_MAIN_DISCHARGE_POSITIVE,
    CONF_MAIN_POWER,
    CONF_MAIN_SOC,
    CONF_MAX_CHARGE_POWER,
    CONF_MAX_HOUSE_FEED,
    CONF_MODE_MANUAL_VALUE,
    CONF_MODE_SELECT,
    DEACT_ALL_ZERO,
    DEACT_RESTORE,
    DEFAULT_BALCONY_DISCHARGE_POSITIVE,
    DEFAULT_CHARGE_HEADROOM,
    DEFAULT_DEACTIVATION_BEHAVIOR,
    DEFAULT_DEADBAND,
    DEFAULT_DISCHARGE_OFF_THRESHOLD,
    DEFAULT_DISCHARGE_ON_THRESHOLD,
    DEFAULT_DISCHARGE_SHARE,
    DEFAULT_FAILSAFE_AFTER,
    DEFAULT_GRID_EXPORT_POSITIVE,
    DEFAULT_GRID_IMPORT_OFF_THRESHOLD,
    DEFAULT_GRID_IMPORT_ON_THRESHOLD,
    DEFAULT_GRID_SUPPORT_ENABLED,
    DEFAULT_INTERVAL,
    DEFAULT_MAIN_DISCHARGE_POSITIVE,
    DEFAULT_MAIN_EMPTY_SOC,
    DEFAULT_MAX_CHARGE_POWER,
    DEFAULT_MAX_HOUSE_FEED,
    DOMAIN,
)

# --- reusable selectors ----------------------------------------------------
_SENSOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor")
)
_NUMBER_ENTITY = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=["number", "input_number"])
)
_SELECT_ENTITY = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=["select", "input_select"])
)
_SWITCH_ENTITY = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=["switch", "input_boolean"])
)
_BOOL = selector.BooleanSelector()
_TEXT = selector.TextSelector()


def _power(maximum: int = 5000) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0, max=maximum, step=1, unit_of_measurement="W",
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _seconds() -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0, max=86400, step=1, unit_of_measurement="s",
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _percent() -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0, max=100, step=1, unit_of_measurement="%",
            mode=selector.NumberSelectorMode.SLIDER,
        )
    )


_DEACT_SELECT = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[DEACT_ALL_ZERO, DEACT_RESTORE],
        translation_key="deactivation_behavior",
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)


def _inputs_schema(d: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_GRID_POWER, default=d.get(CONF_GRID_POWER)): _SENSOR,
            vol.Required(
                CONF_GRID_EXPORT_POSITIVE,
                default=d.get(CONF_GRID_EXPORT_POSITIVE, DEFAULT_GRID_EXPORT_POSITIVE),
            ): _BOOL,
            vol.Required(CONF_MAIN_SOC, default=d.get(CONF_MAIN_SOC)): _SENSOR,
            vol.Required(CONF_MAIN_POWER, default=d.get(CONF_MAIN_POWER)): _SENSOR,
            vol.Required(
                CONF_MAIN_DISCHARGE_POSITIVE,
                default=d.get(
                    CONF_MAIN_DISCHARGE_POSITIVE, DEFAULT_MAIN_DISCHARGE_POSITIVE
                ),
            ): _BOOL,
            vol.Required(CONF_BALCONY_SOC, default=d.get(CONF_BALCONY_SOC)): _SENSOR,
            vol.Required(CONF_BALCONY_POWER, default=d.get(CONF_BALCONY_POWER)): _SENSOR,
            vol.Required(
                CONF_BALCONY_DISCHARGE_POSITIVE,
                default=d.get(
                    CONF_BALCONY_DISCHARGE_POSITIVE,
                    DEFAULT_BALCONY_DISCHARGE_POSITIVE,
                ),
            ): _BOOL,
        }
    )


def _control_schema(d: dict[str, Any]) -> vol.Schema:
    # vol.Optional fields with no stored value must be omitted from defaults,
    # otherwise the selector renders "None". Use suggested_value via description.
    def opt(key: str):
        existing = d.get(key)
        if existing is not None:
            return vol.Optional(key, description={"suggested_value": existing})
        return vol.Optional(key)

    return vol.Schema(
        {
            opt(CONF_MODE_SELECT): _SELECT_ENTITY,
            opt(CONF_MODE_MANUAL_VALUE): _TEXT,
            vol.Required(
                CONF_DISCHARGE_NUMBER, default=d.get(CONF_DISCHARGE_NUMBER)
            ): _NUMBER_ENTITY,
            opt(CONF_AC_CHARGE_SWITCH): _SWITCH_ENTITY,
            opt(CONF_AC_CHARGE_NUMBER): _NUMBER_ENTITY,
            vol.Required(
                CONF_DEACTIVATION_BEHAVIOR,
                default=d.get(
                    CONF_DEACTIVATION_BEHAVIOR, DEFAULT_DEACTIVATION_BEHAVIOR
                ),
            ): _DEACT_SELECT,
            opt(CONF_DEACTIVATION_MODE_VALUE): _TEXT,
        }
    )


def _params_schema(d: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_MAX_CHARGE_POWER,
                default=d.get(CONF_MAX_CHARGE_POWER, DEFAULT_MAX_CHARGE_POWER),
            ): _power(),
            vol.Required(
                CONF_MAX_HOUSE_FEED,
                default=d.get(CONF_MAX_HOUSE_FEED, DEFAULT_MAX_HOUSE_FEED),
            ): _power(),
            vol.Required(
                CONF_INTERVAL, default=d.get(CONF_INTERVAL, DEFAULT_INTERVAL)
            ): _seconds(),
            vol.Required(
                CONF_CHARGE_HEADROOM,
                default=d.get(CONF_CHARGE_HEADROOM, DEFAULT_CHARGE_HEADROOM),
            ): _power(),
            vol.Required(
                CONF_DISCHARGE_ON_THRESHOLD,
                default=d.get(
                    CONF_DISCHARGE_ON_THRESHOLD, DEFAULT_DISCHARGE_ON_THRESHOLD
                ),
            ): _power(),
            vol.Required(
                CONF_DISCHARGE_OFF_THRESHOLD,
                default=d.get(
                    CONF_DISCHARGE_OFF_THRESHOLD, DEFAULT_DISCHARGE_OFF_THRESHOLD
                ),
            ): _power(),
            vol.Required(
                CONF_DISCHARGE_SHARE,
                default=d.get(CONF_DISCHARGE_SHARE, DEFAULT_DISCHARGE_SHARE),
            ): _percent(),
            vol.Required(
                CONF_DEADBAND, default=d.get(CONF_DEADBAND, DEFAULT_DEADBAND)
            ): _power(1000),
            vol.Required(
                CONF_FAILSAFE_AFTER,
                default=d.get(CONF_FAILSAFE_AFTER, DEFAULT_FAILSAFE_AFTER),
            ): _seconds(),
            vol.Required(
                CONF_GRID_SUPPORT_ENABLED,
                default=d.get(
                    CONF_GRID_SUPPORT_ENABLED, DEFAULT_GRID_SUPPORT_ENABLED
                ),
            ): _BOOL,
            vol.Required(
                CONF_MAIN_EMPTY_SOC,
                default=d.get(CONF_MAIN_EMPTY_SOC, DEFAULT_MAIN_EMPTY_SOC),
            ): _percent(),
            vol.Required(
                CONF_GRID_IMPORT_ON_THRESHOLD,
                default=d.get(
                    CONF_GRID_IMPORT_ON_THRESHOLD, DEFAULT_GRID_IMPORT_ON_THRESHOLD
                ),
            ): _power(),
            vol.Required(
                CONF_GRID_IMPORT_OFF_THRESHOLD,
                default=d.get(
                    CONF_GRID_IMPORT_OFF_THRESHOLD, DEFAULT_GRID_IMPORT_OFF_THRESHOLD
                ),
            ): _power(),
        }
    )


class BalconyBatteryConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial configuration."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_control()
        return self.async_show_form(
            step_id="user", data_schema=_inputs_schema(self._data)
        )

    async def async_step_control(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_params()
        return self.async_show_form(
            step_id="control", data_schema=_control_schema(self._data)
        )

    async def async_step_params(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(
                title="Balcony Battery Manager", data=self._data
            )
        return self.async_show_form(
            step_id="params", data_schema=_params_schema(self._data)
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return BalconyBatteryOptionsFlow()


class BalconyBatteryOptionsFlow(OptionsFlow):
    """Edit every setting after setup."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    @property
    def _current(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options, **self._data}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_control()
        return self.async_show_form(
            step_id="init", data_schema=_inputs_schema(self._current)
        )

    async def async_step_control(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_params()
        return self.async_show_form(
            step_id="control", data_schema=_control_schema(self._current)
        )

    async def async_step_params(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(title="", data=self._data)
        return self.async_show_form(
            step_id="params", data_schema=_params_schema(self._current)
        )
