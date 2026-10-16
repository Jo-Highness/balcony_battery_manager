"""DataUpdateCoordinator that drives the Solarbank 4 via its actuator entities."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, SUN_EVENT_SUNSET
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.sun import get_astral_event_next
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import const as C, logic, units

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1

type BalconyBatteryConfigEntry = ConfigEntry[BalconyBatteryCoordinator]

# Sensors that must be available; if any is missing we fail safe to 0 W.
_REQUIRED = (
    C.CONF_P_BATT_DRAW,
    C.CONF_P_ANKER_OUT,
    C.CONF_P_GRID,
    C.CONF_SOC_ANKER,
    C.CONF_P_ANKER_PV,
)
_POWER_KEYS = (C.CONF_P_BATT_DRAW, C.CONF_P_ANKER_OUT, C.CONF_P_GRID, C.CONF_P_ANKER_PV)
_PERCENT_KEYS = (C.CONF_SOC_ANKER, C.CONF_MAIN_SOC)

_UNAVAILABLE = ("unknown", "unavailable", "", None)


class ActuatorError(HomeAssistantError):
    """An actuator write failed or timed out."""


class BalconyBatteryCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Reads live signals, decides one mode per cycle, writes the setpoints."""

    config_entry: BalconyBatteryConfigEntry

    def __init__(self, hass: HomeAssistant, entry: BalconyBatteryConfigEntry) -> None:
        self.entry = entry
        self._opts: dict[str, Any] = {**entry.data, **entry.options}
        interval = int(self._opts.get(C.CONF_INTERVAL, C.DEFAULT_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=C.DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self._cfg = C.build_cfg(self._opts)
        self._state = logic.ControllerState()
        self._enabled = True
        self._lock = asyncio.Lock()
        self._last_cycle: datetime | None = None
        # (grid_flow, power in W) last written to the device; None = unknown.
        self._last_written: tuple[str, float] | None = None
        self._applied_w = 0.0
        self._unit_warned: set[str] = set()
        self._number_missing_logged = False
        # Persist the master switch so a deliberate "off" survives a restart
        # instead of silently re-enabling control.
        self._store: Store = Store(hass, STORAGE_VERSION, f"{C.DOMAIN}.{entry.entry_id}")

    async def async_setup(self) -> None:
        stored = await self._store.async_load()
        if isinstance(stored, dict) and C.KEY_ENABLED in stored:
            self._enabled = bool(stored[C.KEY_ENABLED])
        await self.async_config_entry_first_refresh()

    async def _async_save_enabled(self) -> None:
        await self._store.async_save({C.KEY_ENABLED: self._enabled})

    @property
    def enabled(self) -> bool:
        """Whether the control loop is enabled (master switch)."""
        return self._enabled

    # ---- master switch / services -------------------------------------
    async def async_enable(self) -> None:
        async with self._lock:
            self._enabled = True
            await self._async_save_enabled()
        await self.async_recalculate_now()

    async def async_disable(self) -> None:
        """Disable control and bring the Solarbank into a safe state.

        Holds the cycle lock, so a running cycle finishes first and no cycle
        can write a non-zero setpoint afterwards (it sees ``enabled=False``).
        """
        async with self._lock:
            self._enabled = False
            await self._async_save_enabled()
            await self._async_release(restore_mode=True)
            self._state = logic.ControllerState()
            self.async_set_updated_data(self._disabled_data())

    async def async_release_on_unload(self) -> None:
        """Set the power to 0 W when the entry is unloaded (no mode restore)."""
        async with self._lock:
            await self._async_release(restore_mode=False)

    async def async_recalculate_now(self) -> None:
        await self.async_request_refresh()

    def diagnostics(self) -> dict[str, Any]:
        """Internal controller state for diagnostics."""
        return {
            "enabled": self._enabled,
            "last_written": self._last_written,
            "applied_w": self._applied_w,
            "controller": {
                "discharge_step": self._state.discharge.step_index,
                "discharge_up_timers": self._state.discharge.up_timers,
                "discharge_down_timers": self._state.discharge.down_timers,
                "last_charge_w": self._state.last_charge_w,
                "grid_support_on": self._state.grid_support_on,
                "last_support_w": self._state.last_support_w,
            },
            "cfg": self._cfg,
        }

    # ---- helpers ------------------------------------------------------
    def _warn_unit_once(self, eid: str, unit: Any) -> None:
        if eid not in self._unit_warned:
            self._unit_warned.add(eid)
            _LOGGER.warning("%s reports unsupported unit %r; treating it as unavailable", eid, unit)

    def _num(self, key: str) -> float | None:
        """Read a sensor value normalised to W (power) or % (SoC).

        Returns None if missing/unavailable/non-numeric or if the unit is not
        supported (logged once).
        """
        eid = self._opts.get(key)
        if not eid:
            return None
        st = self.hass.states.get(eid)
        if st is None or st.state in _UNAVAILABLE:
            return None
        try:
            raw = float(st.state)
        except (ValueError, TypeError):
            return None
        table = units.PERCENT if key in _PERCENT_KEYS else units.POWER_TO_W
        unit = st.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        value = units.convert(raw, unit, table)
        if value is None:
            self._warn_unit_once(eid, unit)
        return value

    def _signed(
        self, key: str, positive_flag_key: str, positive_default: bool, positive_meaning: bool
    ) -> float | None:
        """Normalise a signed sensor to a desired positive convention.

        positive_meaning=True  -> caller wants the "positive" quantity
        (e.g. discharge-into-house or export) to come out positive.
        """
        raw = self._num(key)
        if raw is None:
            return None
        flag = self._opts.get(positive_flag_key, positive_default)
        # If the sensor already encodes positive==meaning, keep sign, else flip.
        return raw if flag == positive_meaning else -raw

    def _number_scale(self) -> tuple[float, float, float] | None:
        """(min W, max W, W per number unit) of the target-power number.

        None if the number does not exist or reports an unsupported unit.
        """
        eid = self._opts.get(C.CONF_TARGET_POWER_NUMBER)
        st = self.hass.states.get(eid) if eid else None
        if st is None:
            return None
        unit = st.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        f = units.factor(unit, units.POWER_TO_W)
        if f is None:
            self._warn_unit_once(eid, unit)
            return None
        try:
            lo = float(st.attributes.get("min", 0)) * f
            hi = float(st.attributes.get("max", 1e9)) * f
        except (ValueError, TypeError):
            return None
        return max(lo, 0.0), hi, f

    def _number_available(self) -> bool:
        """Whether the target-power number exists and can be written."""
        eid = self._opts.get(C.CONF_TARGET_POWER_NUMBER)
        st = self.hass.states.get(eid) if eid else None
        if st is None or st.state in _UNAVAILABLE:
            if not self._number_missing_logged:
                self._number_missing_logged = True
                _LOGGER.warning("Target power number %s is unavailable; cannot write", eid)
            return False
        self._number_missing_logged = False
        return True

    def _effective_cfg(self) -> dict[str, Any]:
        """Tunables with the closed-loop limits capped at the device maximum."""
        cfg = dict(self._cfg)
        scale = self._number_scale()
        if scale is not None:
            hi = scale[1]
            cfg["max_charge"] = min(cfg["max_charge"], hi)
            cfg["grid_support_max"] = min(cfg["grid_support_max"], hi)
        return cfg

    def _disabled_data(self) -> dict[str, Any]:
        return {
            **(self.data or {}),
            C.KEY_ENABLED: False,
            C.KEY_MODE: C.MODE_DISABLED,
            C.KEY_TARGET_POWER: 0.0,
            "grid_flow": "",
            "reason": "Disabled",
        }

    async def _async_update_data(self) -> dict[str, Any]:
        async with self._lock:
            return await self._cycle()

    async def _cycle(self) -> dict[str, Any]:
        now = dt_util.utcnow()
        # The very first cycle integrates over one configured interval.
        dt_s = self.update_interval.total_seconds() if self.update_interval else C.DEFAULT_INTERVAL
        if self._last_cycle is not None:
            dt_s = max(1.0, (now - self._last_cycle).total_seconds())
        self._last_cycle = now

        if not self._enabled:
            return self._disabled_data()

        # Fail-safe: any required sensor missing -> 0 W, controller state reset
        # (staircase timers must not keep running across an outage).
        if any(self._num(k) is None for k in _REQUIRED):
            self._state = logic.ControllerState()
            dec = logic.failsafe_decision()
            await self._apply(dec)
            _LOGGER.warning("Fail-safe: required sensor unavailable -> 0 W")
            return self._as_data(dec)

        p_batt = self._signed(
            C.CONF_P_BATT_DRAW, C.CONF_BATT_DRAW_POSITIVE, C.DEFAULT_BATT_DRAW_POSITIVE, True
        )
        p_out = self._num(C.CONF_P_ANKER_OUT) or 0.0
        surplus = self._signed(
            C.CONF_P_GRID, C.CONF_GRID_EXPORT_POSITIVE, C.DEFAULT_GRID_EXPORT_POSITIVE, True
        )
        soc = self._num(C.CONF_SOC_ANKER)
        pv = self._num(C.CONF_P_ANKER_PV) or 0.0
        main_soc = self._num(C.CONF_MAIN_SOC)  # optional; enables grid support
        sunset = self._sunset(now)

        dec = logic.decide(
            self._state,
            # Local time: the afternoon cap boundary is a local wall-clock hour.
            now=dt_util.as_local(now),
            sunset=sunset,
            p_batt_draw=p_batt,
            p_anker_out=p_out,
            grid_export=surplus,
            soc=soc,
            p_anker_pv=pv,
            dt_s=dt_s,
            cfg=self._effective_cfg(),
            main_soc=main_soc,
        )
        applied = await self._apply(dec)
        logic.sync_applied(self._state, dec.mode, applied)
        return self._as_data(dec)

    def _sunset(self, now: datetime) -> datetime:
        """Next sunset: sun entity -> astral calculation -> fixed fallback hour."""
        eid = self._opts.get(C.CONF_SUN) or "sun.sun"
        st = self.hass.states.get(eid)
        if st is not None:
            nxt = st.attributes.get("next_setting")
            if nxt:
                parsed = dt_util.parse_datetime(str(nxt))
                if parsed:
                    return dt_util.as_utc(parsed)
        try:
            return dt_util.as_utc(
                get_astral_event_next(self.hass, SUN_EVENT_SUNSET, utc_point_in_time=now)
            )
        except (ValueError, AttributeError):
            pass
        local = dt_util.as_local(now)
        target = local.replace(hour=C.FALLBACK_SUNSET_HOUR, minute=0, second=0, microsecond=0)
        if target <= local:
            target += timedelta(days=1)
        return dt_util.as_utc(target)

    # ---- actuator writes ----------------------------------------------
    def _flow_option(self, flow: str) -> str:
        if flow == "discharge":
            return self._opts.get(C.CONF_GRID_FLOW_DISCHARGE, C.DEFAULT_GRID_FLOW_DISCHARGE)
        return self._opts.get(C.CONF_GRID_FLOW_CHARGE, C.DEFAULT_GRID_FLOW_CHARGE)

    def _needs_write(self, flow: str, power: float) -> bool:
        last = self._last_written
        if last is None or last[0] != flow:
            return True
        if power == 0.0:
            return last[1] != 0.0
        deadband = float(self._opts.get(C.CONF_DEADBAND, C.DEFAULT_DEADBAND))
        return abs(last[1] - power) >= deadband

    async def _apply(self, dec: logic.Decision) -> float:
        """Write the decided setpoint; return the power (W) now in effect.

        Safety rules:
        * the power is clamped to the number entity's own min/max;
        * the direction is never switched under load: power -> 0 W, then
          switch the grid-flow select, then write the new setpoint;
        * every write is awaited (blocking) with a timeout;
        * any failure falls back to writing 0 W.
        """
        number_eid = self._opts.get(C.CONF_TARGET_POWER_NUMBER)
        select_eid = self._opts.get(C.CONF_GRID_FLOW_SELECT)
        if not number_eid:
            return 0.0
        if not self._number_available():
            # Nothing can be written; force a full rewrite once it is back.
            self._last_written = None
            self._applied_w = 0.0
            return 0.0
        flow = dec.grid_flow  # "" when idle/failsafe -> power 0 only
        scale = self._number_scale()
        if flow and scale is None:
            _LOGGER.error("Target power number %s unavailable or unsupported unit", number_eid)
            flow = ""
        power = logic.clamp(dec.target_power, scale[0], scale[1]) if flow and scale else 0.0
        if not flow:
            power = 0.0

        try:
            if flow:
                await self._async_ensure_mode(self._opts.get(C.CONF_CONTROL_MODE))
            option = self._flow_option(flow) if flow else None
            cur = self.hass.states.get(select_eid) if select_eid else None
            if select_eid and option and (cur is None or cur.state != option):
                if self._last_written is None or self._last_written[1] != 0.0:
                    await self._async_set_power(0.0)
                await self._async_select(select_eid, option)
                await self._async_set_power(power, flow)
            elif self._needs_write(flow, power):
                await self._async_set_power(power, flow)
        except ActuatorError as err:
            _LOGGER.error("Actuator write failed (%s); falling back to 0 W", err)
            self._last_written = None
            try:
                await self._async_set_power(0.0)
            except ActuatorError as err2:
                _LOGGER.error("Fail-safe write of 0 W failed as well: %s", err2)
            self._applied_w = 0.0
            return 0.0
        self._applied_w = self._last_written[1] if self._last_written else 0.0
        return self._applied_w

    async def _async_release(self, *, restore_mode: bool) -> None:
        """Set the power to 0 W and optionally hand control back to Anker."""
        if self._number_available():
            try:
                await self._async_set_power(0.0)
            except ActuatorError as err:
                self._last_written = None
                _LOGGER.error("Could not set the Solarbank to 0 W: %s", err)
        self._applied_w = 0.0
        if restore_mode:
            try:
                await self._async_ensure_mode(self._opts.get(C.CONF_RESTORE_MODE))
            except ActuatorError as err:
                _LOGGER.error("Could not restore the Anker operating mode: %s", err)

    async def _async_ensure_mode(self, option: str | None) -> None:
        eid = self._opts.get(C.CONF_MODE_SELECT)
        if not eid or not option:
            return
        cur = self.hass.states.get(eid)
        if cur is None or cur.state != option:
            await self._async_select(eid, option)

    async def _async_call(self, domain: str, service: str, data: dict[str, Any]) -> None:
        try:
            async with asyncio.timeout(C.SERVICE_TIMEOUT):
                await self.hass.services.async_call(domain, service, data, blocking=True)
        except TimeoutError as err:
            raise ActuatorError(f"{domain}.{service} {data} timed out") from err
        except (HomeAssistantError, ValueError) as err:
            raise ActuatorError(f"{domain}.{service} {data}: {err}") from err

    async def _async_set_power(self, watts: float, flow: str = "") -> None:
        eid = self._opts[C.CONF_TARGET_POWER_NUMBER]
        scale = self._number_scale()
        f = scale[2] if scale else 1.0
        if watts != 0.0 and scale is None:
            raise ActuatorError(f"{eid}: cannot scale {watts} W")
        value: float = round(watts) if f == 1.0 else round(watts / f, 3)
        domain = eid.split(".", 1)[0]  # number | input_number
        await self._async_call(domain, "set_value", {"entity_id": eid, "value": value})
        self._last_written = (flow, float(watts))

    async def _async_select(self, entity_id: str, option: str) -> None:
        domain = entity_id.split(".", 1)[0]  # select | input_select
        await self._async_call(domain, "select_option", {"entity_id": entity_id, "option": option})

    def _as_data(self, dec: logic.Decision) -> dict[str, Any]:
        return {
            C.KEY_ENABLED: self._enabled,
            C.KEY_MODE: dec.mode,
            C.KEY_TARGET_POWER: dec.target_power,
            C.KEY_DEMAND: dec.demand,
            C.KEY_SURPLUS: dec.surplus,
            "grid_flow": dec.grid_flow,
            "applied_power": self._applied_w,
            "charge_release": dec.charge_release,
            "need_wh": dec.need_wh,
            "rest_pv_wh": dec.rest_pv_wh,
            "reason": dec.reason,
        }
