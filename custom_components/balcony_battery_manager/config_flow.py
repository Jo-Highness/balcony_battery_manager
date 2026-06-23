"""Config & options flow for Balcony Battery Manager."""

from __future__ import annotations

import logging
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
    CONF_BALCONY_POWER_UNIT,
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
    CONF_GRID_POWER_UNIT,
    CONF_GRID_SUPPORT_ENABLED,
    CONF_INTERVAL,
    CONF_MAIN_EMPTY_SOC,
    CONF_MAIN_DISCHARGE_POSITIVE,
    CONF_MAIN_POWER,
    CONF_MAIN_POWER_UNIT,
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
    DEFAULT_POWER_UNIT,
    DOMAIN,
    POWER_UNIT_OPTIONS,
)
from .prefill import (
    suggested_from_anker,
    suggested_from_e3dc,
    suggested_inputs_from_energy,
)

_LOGGER = logging.getLogger(__name__)

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

_POWER_UNIT_SELECT = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=POWER_UNIT_OPTIONS,
        translation_key="power_unit",
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)


def _prefill_value(
    d: dict[str, Any], suggestions: dict[str, Any] | None, key: str
) -> Any:
    """Resolve the value used to pre-fill a field.

    An existing stored value always wins; only when a field is still empty do
    we fall back to a best-effort ``suggestions`` entry (energy dashboard /
    anker_solix). ``None`` means "render the field empty".
    """
    val = d.get(key)
    if val is None and suggestions:
        val = suggestions.get(key)
    return val


def _inputs_schema(
    d: dict[str, Any], suggestions: dict[str, Any] | None = None
) -> vol.Schema:
    # Sensor fields use suggested_value (not default) so a missing/empty
    # pre-fill renders as a blank selector instead of literal "None".
    def sensor(key: str):
        val = _prefill_value(d, suggestions, key)
        if val is not None:
            return vol.Required(key, description={"suggested_value": val})
        return vol.Required(key)

    def sensor_opt(key: str):
        # Optional sensor: e.g. the main-battery SOC, which some roof systems
        # (E3DC via KNX) simply do not expose. Without it grid-support is just
        # skipped; the rest of the control loop runs normally.
        val = _prefill_value(d, suggestions, key)
        if val is not None:
            return vol.Optional(key, description={"suggested_value": val})
        return vol.Optional(key)

    def unit(key: str):
        return vol.Required(key, default=d.get(key, DEFAULT_POWER_UNIT))

    def flag(key: str, fallback: bool):
        # Sign booleans always render, so a stored value / best-effort vendor
        # suggestion / fallback is carried straight in ``default``.
        val = _prefill_value(d, suggestions, key)
        return vol.Required(key, default=fallback if val is None else val)

    return vol.Schema(
        {
            sensor(CONF_GRID_POWER): _SENSOR,
            unit(CONF_GRID_POWER_UNIT): _POWER_UNIT_SELECT,
            flag(CONF_GRID_EXPORT_POSITIVE, DEFAULT_GRID_EXPORT_POSITIVE): _BOOL,
            sensor_opt(CONF_MAIN_SOC): _SENSOR,
            sensor(CONF_MAIN_POWER): _SENSOR,
            unit(CONF_MAIN_POWER_UNIT): _POWER_UNIT_SELECT,
            flag(CONF_MAIN_DISCHARGE_POSITIVE, DEFAULT_MAIN_DISCHARGE_POSITIVE): _BOOL,
            sensor(CONF_BALCONY_SOC): _SENSOR,
            sensor(CONF_BALCONY_POWER): _SENSOR,
            unit(CONF_BALCONY_POWER_UNIT): _POWER_UNIT_SELECT,
            flag(
                CONF_BALCONY_DISCHARGE_POSITIVE, DEFAULT_BALCONY_DISCHARGE_POSITIVE
            ): _BOOL,
        }
    )


def _control_schema(
    d: dict[str, Any], suggestions: dict[str, str] | None = None
) -> vol.Schema:
    # vol.Optional/Required fields with no stored value must be omitted from
    # defaults, otherwise the selector renders "None". Use suggested_value via
    # description (which also carries the best-effort anker_solix pre-fill).
    def opt(key: str):
        val = _prefill_value(d, suggestions, key)
        if val is not None:
            return vol.Optional(key, description={"suggested_value": val})
        return vol.Optional(key)

    def req(key: str):
        val = _prefill_value(d, suggestions, key)
        if val is not None:
            return vol.Required(key, description={"suggested_value": val})
        return vol.Required(key)

    return vol.Schema(
        {
            opt(CONF_MODE_SELECT): _SELECT_ENTITY,
            opt(CONF_MODE_MANUAL_VALUE): _TEXT,
            req(CONF_DISCHARGE_NUMBER): _NUMBER_ENTITY,
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
        # Best-effort pre-fill suggestions, computed once on the first form and
        # reused across steps. Only ever applied to still-empty fields.
        self._suggestions: dict[str, Any] | None = None

    async def _async_prefill(self) -> dict[str, Any]:
        """Collect best-effort suggestions for the initial form.

        Sources are tried in order of confidence — energy dashboard, then the
        E3DC roof-system pattern, then anker_solix — and only ever fill a field
        that no earlier source already resolved (``setdefault``).
        """
        suggestions: dict[str, Any] = {}
        try:
            for resolver in (
                suggested_inputs_from_energy,
                suggested_from_e3dc,
                suggested_from_anker,
            ):
                for key, value in (await resolver(self.hass)).items():
                    suggestions.setdefault(key, value)
        except Exception:  # noqa: BLE001 - pre-fill must never break the flow
            _LOGGER.debug("Config-flow pre-fill failed", exc_info=True)
        return suggestions

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_control()
        if self._suggestions is None:
            self._suggestions = await self._async_prefill()
        return self.async_show_form(
            step_id="user",
            data_schema=_inputs_schema(self._data, self._suggestions),
        )

    async def async_step_control(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_params()
        return self.async_show_form(
            step_id="control",
            data_schema=_control_schema(self._data, self._suggestions),
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
