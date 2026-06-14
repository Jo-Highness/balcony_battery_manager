"""Central control logic for Balcony Battery Manager.

A single :class:`BalconyBatteryCoordinator` owns the runtime state for one
balcony battery (Anker Solix Solarbank 3). On a fixed interval (default 300 s,
matching the Solarbank's ~5-minute cloud refresh cycle) it reads the house /
main-battery measurements and drives a three-state machine:

    IDLE        -> nothing to do, hold balcony at 0 W
    CHARGING    -> absorb grid export surplus into the balcony battery
    DISCHARGING -> let the balcony battery help the main battery discharge

Design rules baked into this module:

* The reconstruction of the *true* surplus / total battery power uses the
  value the plugin **last sent** (``_last_sent_charge`` / ``_last_sent_discharge``),
  never the balcony power sensor. That sensor lags the cloud by up to ~6 minutes
  and would otherwise make the loop oscillate ("Takten").
* All numeric writes go through the standard HA services
  (``number.set_value`` / ``select.select_option`` / ``switch.turn_on|off``)
  and are gated by a send dead-band so identical commands are not repeated.
* The pure decision step (:meth:`_evaluate`) is I/O-free and therefore unit
  testable; :meth:`_apply` performs the side effects.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_BALCONY_SOC,
    ATTR_DATA_VALID,
    ATTR_DISCHARGE_REASON,
    ATTR_GRID_POWER,
    ATTR_LAST_COMMAND,
    ATTR_LAST_GOOD_DATA,
    ATTR_LAST_SENT_CHARGE,
    ATTR_LAST_SENT_DISCHARGE,
    ATTR_MAIN_DISCHARGE,
    ATTR_MAIN_SOC,
    ATTR_THRESHOLDS,
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
    IGNORED_STATES,
    MODE_CHARGING,
    MODE_DISABLED,
    MODE_DISCHARGING,
    MODE_IDLE,
    REASON_BOTH,
    REASON_GRID_SUPPORT,
    REASON_NONE,
    REASON_RELIEF,
    STORAGE_KEY_PREFIX,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

# Units that have already triggered an "unknown unit" warning, so the log is
# not spammed once per control cycle. Keyed by the normalised (lower-cased)
# unit string; the empty string covers "no unit at all".
_WARNED_UNKNOWN_UNITS: set[str] = set()


def _normalise_power(value: float, unit: str | None, override: str) -> float:
    """Return ``value`` expressed in watts.

    ``override`` is one of ``auto`` / ``W`` / ``kW``:

    * ``kW`` -> always multiply by 1000.
    * ``W``  -> take the value as-is.
    * ``auto`` -> look at ``unit`` (case-insensitive, trimmed): ``kW`` scales by
      1000, ``W`` is unchanged, anything else is treated as watts and warned
      about exactly once.
    """
    if override == "kW":
        return value * 1000.0
    if override == "W":
        return value

    normalised = (unit or "").strip().lower()
    if normalised == "kw":
        return value * 1000.0
    if normalised == "w":
        return value

    if normalised not in _WARNED_UNKNOWN_UNITS:
        _WARNED_UNKNOWN_UNITS.add(normalised)
        _LOGGER.warning(
            "Power sensor reported unit %r, which is neither W nor kW; treating "
            "the value as watts. Set the explicit unit override in the "
            "integration options if this is wrong.",
            unit,
        )
    return value


@dataclass
class Inputs:
    """Normalised, sign-corrected snapshot of the input sensors."""

    grid_export: float  # W, positive == feeding into the grid
    main_discharge: float  # W, positive == main battery discharging
    main_soc: float | None  # %
    balcony_soc: float  # %
    balcony_power: float | None  # W, positive == balcony discharging


@dataclass
class Decision:
    """Result of one (I/O-free) evaluation pass."""

    mode: str
    target_charge: float  # W
    target_discharge: float  # W
    surplus: float  # W, reconstructed grid surplus S
    reason: str = REASON_NONE  # why we are discharging (transparency)


def _to_float(value: Any) -> float | None:
    """Parse a state value into a float, or None if it is not usable."""
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in IGNORED_STATES:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def clamp(value: float, low: float, high: float) -> float:
    """Clamp ``value`` into the inclusive ``[low, high]`` range."""
    return max(low, min(high, value))


class BalconyBatteryCoordinator(DataUpdateCoordinator[dict]):
    """Owns the runtime state machine for one balcony battery."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN)
        self.entry = entry
        self._config = {**entry.data, **entry.options}
        self._store: Store = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY_PREFIX}{entry.entry_id}"
        )
        self._lock = asyncio.Lock()
        self._unsub_timer = None

        # --- persisted runtime state ---
        self.enabled: bool = True
        self.mode: str = MODE_IDLE
        self._last_sent_charge: float = 0.0
        self._last_sent_discharge: float = 0.0

        # --- volatile runtime state ---
        self.surplus: float = 0.0
        self._discharge_reason: str = REASON_NONE
        self._last_inputs: Inputs | None = None
        self._last_command: datetime | None = None
        self._last_good: datetime | None = None
        self._data_valid: bool = False

    # ------------------------------------------------------------------ config
    def _opt(self, key: str, default: Any) -> Any:
        return self._config.get(key, default)

    @property
    def interval(self) -> int:
        return int(self._opt(CONF_INTERVAL, DEFAULT_INTERVAL))

    @property
    def max_charge(self) -> float:
        return float(self._opt(CONF_MAX_CHARGE_POWER, DEFAULT_MAX_CHARGE_POWER))

    @property
    def max_house_feed(self) -> float:
        return float(self._opt(CONF_MAX_HOUSE_FEED, DEFAULT_MAX_HOUSE_FEED))

    @property
    def headroom(self) -> float:
        return float(self._opt(CONF_CHARGE_HEADROOM, DEFAULT_CHARGE_HEADROOM))

    @property
    def on_threshold(self) -> float:
        return float(
            self._opt(CONF_DISCHARGE_ON_THRESHOLD, DEFAULT_DISCHARGE_ON_THRESHOLD)
        )

    @property
    def off_threshold(self) -> float:
        return float(
            self._opt(CONF_DISCHARGE_OFF_THRESHOLD, DEFAULT_DISCHARGE_OFF_THRESHOLD)
        )

    @property
    def share(self) -> float:
        return float(self._opt(CONF_DISCHARGE_SHARE, DEFAULT_DISCHARGE_SHARE)) / 100.0

    @property
    def deadband(self) -> float:
        return float(self._opt(CONF_DEADBAND, DEFAULT_DEADBAND))

    @property
    def failsafe_after(self) -> int:
        return int(self._opt(CONF_FAILSAFE_AFTER, DEFAULT_FAILSAFE_AFTER))

    @property
    def grid_support_enabled(self) -> bool:
        return bool(self._opt(CONF_GRID_SUPPORT_ENABLED, DEFAULT_GRID_SUPPORT_ENABLED))

    @property
    def main_empty_soc(self) -> float:
        return float(self._opt(CONF_MAIN_EMPTY_SOC, DEFAULT_MAIN_EMPTY_SOC))

    @property
    def grid_import_on(self) -> float:
        return float(
            self._opt(CONF_GRID_IMPORT_ON_THRESHOLD, DEFAULT_GRID_IMPORT_ON_THRESHOLD)
        )

    @property
    def grid_import_off(self) -> float:
        return float(
            self._opt(CONF_GRID_IMPORT_OFF_THRESHOLD, DEFAULT_GRID_IMPORT_OFF_THRESHOLD)
        )

    @property
    def grid_power_unit(self) -> str:
        return str(self._opt(CONF_GRID_POWER_UNIT, DEFAULT_POWER_UNIT))

    @property
    def main_power_unit(self) -> str:
        return str(self._opt(CONF_MAIN_POWER_UNIT, DEFAULT_POWER_UNIT))

    @property
    def balcony_power_unit(self) -> str:
        return str(self._opt(CONF_BALCONY_POWER_UNIT, DEFAULT_POWER_UNIT))

    # ------------------------------------------------------------------ setup
    async def async_setup(self) -> None:
        """Restore persisted state and start the control timer."""
        await self._async_restore()
        self._schedule_timer()
        # Push an initial data snapshot so entities have something to show.
        self.async_set_updated_data(self._build_data())

    def _schedule_timer(self) -> None:
        if self._unsub_timer is not None:
            self._unsub_timer()
        self._unsub_timer = async_track_time_interval(
            self.hass, self._async_timer_tick, timedelta(seconds=self.interval)
        )

    async def async_shutdown(self) -> None:  # type: ignore[override]
        if self._unsub_timer is not None:
            self._unsub_timer()
            self._unsub_timer = None
        await super().async_shutdown()

    # ------------------------------------------------------------------ store
    async def _async_restore(self) -> None:
        data = await self._store.async_load()
        if not data:
            return
        self.enabled = bool(data.get("enabled", True))
        self.mode = data.get("mode", MODE_IDLE)
        self._last_sent_charge = float(data.get("last_sent_charge", 0.0))
        self._last_sent_discharge = float(data.get("last_sent_discharge", 0.0))
        _LOGGER.debug(
            "Restored state: enabled=%s mode=%s charge=%s discharge=%s",
            self.enabled,
            self.mode,
            self._last_sent_charge,
            self._last_sent_discharge,
        )

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "enabled": self.enabled,
                "mode": self.mode,
                "last_sent_charge": self._last_sent_charge,
                "last_sent_discharge": self._last_sent_discharge,
            }
        )

    # ------------------------------------------------------------------ public
    async def async_enable(self) -> None:
        if not self.enabled:
            self.enabled = True
            _LOGGER.info("Balcony Battery Manager enabled")
            await self._async_save()
        await self.async_recalculate_now()

    async def async_disable(self) -> None:
        self.enabled = False
        _LOGGER.info("Balcony Battery Manager disabled")
        async with self._lock:
            await self._apply_deactivation()
            self.mode = MODE_DISABLED
            await self._async_save()
            self.async_set_updated_data(self._build_data())

    async def async_recalculate_now(self) -> None:
        """Run one control cycle immediately, outside the timer."""
        await self._async_control()

    @callback
    def _async_timer_tick(self, _now: datetime) -> None:
        self.hass.async_create_task(self._async_control())

    # ------------------------------------------------------------------ inputs
    def _read_inputs(self) -> Inputs | None:
        """Read & sign-normalise the input sensors.

        Returns ``None`` when a required input is missing/unavailable or
        obviously misconfigured (defensive behaviour, see README).
        """
        grid_state, grid_unit = self._state_with_unit(CONF_GRID_POWER)
        main_state, main_unit = self._state_with_unit(CONF_MAIN_POWER)
        grid_raw = _to_float(grid_state)
        main_raw = _to_float(main_state)
        balcony_soc = _to_float(self._state(CONF_BALCONY_SOC))

        if grid_raw is None or main_raw is None or balcony_soc is None:
            return None

        # Defensive: SOC must be a sane percentage.
        if balcony_soc < 0 or balcony_soc > 100:
            _LOGGER.warning("Balcony SOC out of range (%s%%), ignoring cycle", balcony_soc)
            return None
        balcony_soc = clamp(balcony_soc, 0, 100)

        # Order per input: parse float -> normalise unit to W -> sign-correct.
        grid_w = _normalise_power(grid_raw, grid_unit, self.grid_power_unit)
        main_w = _normalise_power(main_raw, main_unit, self.main_power_unit)

        export_positive = self._opt(CONF_GRID_EXPORT_POSITIVE, DEFAULT_GRID_EXPORT_POSITIVE)
        grid_export = grid_w if export_positive else -grid_w

        main_disch_positive = self._opt(
            CONF_MAIN_DISCHARGE_POSITIVE, DEFAULT_MAIN_DISCHARGE_POSITIVE
        )
        main_discharge = main_w if main_disch_positive else -main_w

        # Optional / informational inputs. SOC stays a percentage (no scaling).
        main_soc = _to_float(self._state(CONF_MAIN_SOC))
        balcony_state, balcony_unit = self._state_with_unit(CONF_BALCONY_POWER)
        balcony_power_raw = _to_float(balcony_state)
        balcony_power = None
        if balcony_power_raw is not None:
            balcony_w = _normalise_power(
                balcony_power_raw, balcony_unit, self.balcony_power_unit
            )
            balcony_disch_positive = self._opt(
                CONF_BALCONY_DISCHARGE_POSITIVE, DEFAULT_BALCONY_DISCHARGE_POSITIVE
            )
            balcony_power = balcony_w if balcony_disch_positive else -balcony_w

        return Inputs(
            grid_export=grid_export,
            main_discharge=main_discharge,
            main_soc=main_soc,
            balcony_soc=balcony_soc,
            balcony_power=balcony_power,
        )

    def _state(self, conf_key: str) -> Any:
        entity_id = self._config.get(conf_key)
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        return state.state if state else None

    def _state_with_unit(self, conf_key: str) -> tuple[Any, str | None]:
        """Return ``(state, unit_of_measurement)`` for a configured entity."""
        entity_id = self._config.get(conf_key)
        if not entity_id:
            return None, None
        state = self.hass.states.get(entity_id)
        if not state:
            return None, None
        return state.state, state.attributes.get("unit_of_measurement")

    # ------------------------------------------------------------------ logic
    def _evaluate(self, inp: Inputs) -> Decision:
        """Pure decision step. No side effects, no I/O.

        Uses the *last sent* setpoints (not the lagging balcony sensor) to
        reconstruct the true grid surplus / total battery discharge / grid
        deficit.
        """
        # Reconstruct the true surplus: our own charging lowers the measured
        # export, so add back what we are currently asking the battery to draw.
        surplus = inp.grid_export + self._last_sent_charge

        already_discharging = self.mode == MODE_DISCHARGING

        # --- discharge trigger A: relieve the main battery (50/50 sharing) ---
        if already_discharging:
            relief_active = inp.main_discharge >= self.off_threshold
        else:
            relief_active = inp.main_discharge > self.on_threshold

        # --- discharge trigger B: main battery empty -> cover grid import ---
        # The balcony's own output hides part of the grid import, so we add it
        # back: grid_deficit = last_sent_discharge - grid_export (signed export).
        grid_deficit = self._last_sent_discharge - inp.grid_export
        main_empty = (
            inp.main_soc is not None and inp.main_soc <= self.main_empty_soc
        )
        grid_active = (
            self.grid_support_enabled and main_empty and inp.balcony_soc > 0
        )
        if grid_active:
            import_threshold = (
                self.grid_import_off if already_discharging else self.grid_import_on
            )
            grid_active = grid_deficit > import_threshold

        # --- mode arbitration (priority: discharging > charging > idle) ---
        if relief_active or grid_active:
            target_relief = (
                clamp(
                    (inp.main_discharge + self._last_sent_discharge) * self.share,
                    0,
                    self.max_house_feed,
                )
                if relief_active
                else 0.0
            )
            target_grid = (
                clamp(grid_deficit, 0, self.max_house_feed) if grid_active else 0.0
            )
            target_discharge = clamp(
                max(target_relief, target_grid), 0, self.max_house_feed
            )
            if relief_active and grid_active:
                reason = REASON_BOTH
            elif grid_active:
                reason = REASON_GRID_SUPPORT
            else:
                reason = REASON_RELIEF
            return Decision(
                MODE_DISCHARGING, 0.0, target_discharge, surplus, reason
            )

        if inp.balcony_soc < 100 and (surplus - self.headroom) > 0:
            target_charge = clamp(surplus - self.headroom, 0, self.max_charge)
            return Decision(MODE_CHARGING, target_charge, 0.0, surplus)

        return Decision(MODE_IDLE, 0.0, 0.0, surplus)

    async def _async_control(self) -> None:
        """One full control cycle: read -> evaluate -> apply."""
        async with self._lock:
            if not self.enabled:
                return

            inp = self._read_inputs()
            now = dt_util.utcnow()

            if inp is None:
                self._data_valid = False
                stale_for = (
                    (now - self._last_good).total_seconds()
                    if self._last_good
                    else None
                )
                if (
                    self.failsafe_after > 0
                    and stale_for is not None
                    and stale_for > self.failsafe_after
                ):
                    _LOGGER.warning(
                        "Inputs unavailable for %.0fs (> %ss): going to safe state",
                        stale_for,
                        self.failsafe_after,
                    )
                    await self._apply(Decision(MODE_IDLE, 0.0, 0.0, self.surplus))
                else:
                    _LOGGER.warning(
                        "One or more inputs unavailable; holding last safe state"
                    )
                self.async_set_updated_data(self._build_data())
                return

            self._data_valid = True
            self._last_good = now
            self._last_inputs = inp

            decision = self._evaluate(inp)
            await self._apply(decision)
            self.async_set_updated_data(self._build_data())

    # ------------------------------------------------------------------ apply
    async def _apply(self, decision: Decision) -> None:
        """Translate a decision into Anker service calls (with dead-band)."""
        self.surplus = decision.surplus
        self._discharge_reason = (
            decision.reason if decision.mode == MODE_DISCHARGING else REASON_NONE
        )

        if decision.mode == MODE_CHARGING:
            await self._ensure_manual_mode()
            await self._set_ac_charge_switch(True)
            await self._set_ac_charge_power(decision.target_charge)
            await self._set_discharge_power(0.0)
        elif decision.mode == MODE_DISCHARGING:
            await self._ensure_manual_mode()
            await self._set_ac_charge_switch(False)
            await self._set_ac_charge_power(0.0)
            await self._set_discharge_power(decision.target_discharge)
        else:  # IDLE
            await self._ensure_manual_mode()
            await self._set_ac_charge_switch(False)
            await self._set_ac_charge_power(0.0)
            await self._set_discharge_power(0.0)

        if decision.mode != self.mode:
            _LOGGER.info(
                "Mode %s -> %s (charge=%.0fW discharge=%.0fW surplus=%.0fW)",
                self.mode,
                decision.mode,
                decision.target_charge,
                decision.target_discharge,
                decision.surplus,
            )
        self.mode = decision.mode
        await self._async_save()

    async def _apply_deactivation(self) -> None:
        """Run the configured deactivation action when the master switch goes off."""
        behavior = self._opt(CONF_DEACTIVATION_BEHAVIOR, DEFAULT_DEACTIVATION_BEHAVIOR)
        await self._set_ac_charge_switch(False)
        await self._set_ac_charge_power(0.0)
        await self._set_discharge_power(0.0)

        if behavior == DEACT_RESTORE:
            restore_value = self._config.get(CONF_DEACTIVATION_MODE_VALUE)
            select_entity = self._config.get(CONF_MODE_SELECT)
            if select_entity and restore_value:
                _LOGGER.info("Restoring Anker mode to %s", restore_value)
                await self._select_option(select_entity, restore_value)

    # ------------------------------------------------------------------ writers
    async def _ensure_manual_mode(self) -> None:
        select_entity = self._config.get(CONF_MODE_SELECT)
        manual_value = self._config.get(CONF_MODE_MANUAL_VALUE)
        if not select_entity or not manual_value:
            return
        current = self._state(CONF_MODE_SELECT)
        if current == manual_value:
            return
        _LOGGER.debug("Forcing Anker mode select %s -> %s", select_entity, manual_value)
        await self._select_option(select_entity, manual_value)

    async def _set_discharge_power(self, target: float) -> None:
        entity_id = self._config.get(CONF_DISCHARGE_NUMBER)
        if not entity_id:
            return
        if self._exceeds_deadband(target, self._last_sent_discharge):
            await self._set_number(entity_id, target)
        self._last_sent_discharge = target

    async def _set_ac_charge_power(self, target: float) -> None:
        entity_id = self._config.get(CONF_AC_CHARGE_NUMBER)
        if entity_id and self._exceeds_deadband(target, self._last_sent_charge):
            await self._set_number(entity_id, target)
        self._last_sent_charge = target

    async def _set_ac_charge_switch(self, on: bool) -> None:
        entity_id = self._config.get(CONF_AC_CHARGE_SWITCH)
        if not entity_id:
            return
        current = self.hass.states.get(entity_id)
        desired = "on" if on else "off"
        if current is not None and current.state == desired:
            return
        service = SERVICE_TURN_ON if on else SERVICE_TURN_OFF
        await self.hass.services.async_call(
            "switch", service, {ATTR_ENTITY_ID: entity_id}, blocking=True
        )
        self._mark_command()

    def _exceeds_deadband(self, new: float, last: float) -> bool:
        """True if ``new`` differs from the last sent value by > the dead-band."""
        return abs(new - last) > self.deadband

    async def _set_number(self, entity_id: str, value: float) -> None:
        await self.hass.services.async_call(
            "number",
            "set_value",
            {ATTR_ENTITY_ID: entity_id, "value": round(value)},
            blocking=True,
        )
        self._mark_command()

    async def _select_option(self, entity_id: str, option: str) -> None:
        await self.hass.services.async_call(
            "select",
            "select_option",
            {ATTR_ENTITY_ID: entity_id, "option": option},
            blocking=True,
        )
        self._mark_command()

    def _mark_command(self) -> None:
        self._last_command = dt_util.utcnow()

    # ------------------------------------------------------------------ data
    def _build_data(self) -> dict[str, Any]:
        inp = self._last_inputs
        return {
            "enabled": self.enabled,
            "mode": MODE_DISABLED if not self.enabled else self.mode,
            "target_charge": self._last_sent_charge,
            "target_discharge": self._last_sent_discharge,
            "surplus": self.surplus,
            "attrs": {
                ATTR_GRID_POWER: inp.grid_export if inp else None,
                ATTR_MAIN_DISCHARGE: inp.main_discharge if inp else None,
                ATTR_MAIN_SOC: inp.main_soc if inp else None,
                ATTR_BALCONY_SOC: inp.balcony_soc if inp else None,
                ATTR_LAST_SENT_CHARGE: self._last_sent_charge,
                ATTR_LAST_SENT_DISCHARGE: self._last_sent_discharge,
                ATTR_LAST_COMMAND: self._last_command,
                ATTR_LAST_GOOD_DATA: self._last_good,
                ATTR_DATA_VALID: self._data_valid,
                ATTR_DISCHARGE_REASON: self._discharge_reason,
                ATTR_THRESHOLDS: {
                    "headroom": self.headroom,
                    "discharge_on": self.on_threshold,
                    "discharge_off": self.off_threshold,
                    "share": self.share,
                    "max_charge": self.max_charge,
                    "max_house_feed": self.max_house_feed,
                    "deadband": self.deadband,
                },
            },
        }
