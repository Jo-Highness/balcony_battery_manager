"""DataUpdateCoordinator that drives the Solarbank 4 via its actor entities."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import const as C, logic

_LOGGER = logging.getLogger(__name__)

# Sensors that must be available; if any is missing we fail safe to 0/0.
_REQUIRED = (
    C.CONF_P_BATT_DRAW,
    C.CONF_P_ANKER_OUT,
    C.CONF_P_GRID,
    C.CONF_SOC_ANKER,
    C.CONF_P_ANKER_PV,
)


class BalconyBatteryCoordinator(DataUpdateCoordinator[dict]):
    """Reads live signals, decides one mode per cycle, writes the setpoints."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self._opts = {**entry.data, **entry.options}
        interval = int(self._opts.get(C.CONF_INTERVAL, C.DEFAULT_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            name=C.DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self._cfg = C.build_cfg(self._opts)
        self._state = logic.ControllerState()
        self._enabled = True
        self._lock = asyncio.Lock()
        self._last_cycle: datetime | None = None
        self._last_written: tuple[str, float] | None = None

    async def async_setup(self) -> None:
        await self.async_config_entry_first_refresh()

    async def async_shutdown(self) -> None:  # type: ignore[override]
        await super().async_shutdown()

    # ---- master switch / services -------------------------------------
    async def async_enable(self) -> None:
        self._enabled = True
        await self.async_recalculate_now()

    async def async_disable(self) -> None:
        self._enabled = False
        await self._apply(logic.failsafe_decision())
        self.data = {**(self.data or {}), C.KEY_ENABLED: False, C.KEY_MODE: "disabled"}
        self.async_update_listeners()

    async def async_recalculate_now(self) -> None:
        await self.async_request_refresh()

    # ---- helpers ------------------------------------------------------
    def _num(self, key: str) -> float | None:
        """Read a numeric sensor value; None if missing/unavailable."""
        eid = self._opts.get(key)
        if not eid:
            return None
        st = self.hass.states.get(eid)
        if st is None or st.state in ("unknown", "unavailable", "", None):
            return None
        try:
            return float(st.state)
        except (ValueError, TypeError):
            return None

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

    async def _async_update_data(self) -> dict:
        async with self._lock:
            return await self._cycle()

    async def _cycle(self) -> dict:
        now = dt_util.utcnow()
        dt_s = C.DEFAULT_INTERVAL
        if self._last_cycle is not None:
            dt_s = max(1.0, (now - self._last_cycle).total_seconds())
        self._last_cycle = now

        if not self._enabled:
            return {C.KEY_ENABLED: False, C.KEY_MODE: "disabled", C.KEY_TARGET_POWER: 0.0}

        # Fail-safe: any required sensor missing -> 0/0.
        if any(self._num(k) is None for k in _REQUIRED):
            dec = logic.failsafe_decision()
            await self._apply(dec)
            _LOGGER.warning("failsafe: required sensor unavailable -> 0W")
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
            now=now,
            sunset=sunset,
            p_batt_draw=p_batt,
            p_anker_out=p_out,
            grid_export=surplus,
            soc=soc,
            p_anker_pv=pv,
            dt_s=dt_s,
            cfg=self._cfg,
            main_soc=main_soc,
        )
        await self._apply(dec)
        return self._as_data(dec)

    def _sunset(self, now: datetime) -> datetime:
        eid = self._opts.get(C.CONF_SUN)
        if eid:
            st = self.hass.states.get(eid)
            if st is not None:
                nxt = st.attributes.get("next_setting")
                if nxt:
                    try:
                        parsed = dt_util.parse_datetime(nxt)
                        if parsed:
                            return dt_util.as_utc(parsed)
                    except (ValueError, TypeError):
                        pass
        # Fallback: assume sunset ~21:00 local today/tomorrow.
        local = dt_util.as_local(now)
        target = local.replace(hour=21, minute=0, second=0, microsecond=0)
        if target <= local:
            target += timedelta(days=1)
        return dt_util.as_utc(target)

    # ---- actor writes -------------------------------------------------
    async def _apply(self, dec: logic.Decision) -> None:
        """Write the decided setpoint to the Solarbank actor entities.

        Clamp to the number's own min/max. Only write when the change exceeds
        the deadband (or the direction/flow changed).
        """
        number_eid = self._opts.get(C.CONF_TARGET_POWER_NUMBER)
        select_eid = self._opts.get(C.CONF_GRID_FLOW_SELECT)
        power = dec.target_power
        # Clamp to device number limits.
        if number_eid:
            st = self.hass.states.get(number_eid)
            if st is not None:
                lo = float(st.attributes.get("min", 0))
                hi = float(st.attributes.get("max", power))
                power = logic.clamp(power, lo, hi)

        deadband = float(self._opts.get(C.CONF_DEADBAND, C.DEFAULT_DEADBAND))
        flow = dec.grid_flow  # "" when idle/failsafe -> only set power to 0

        # Set direction first (only when actually feeding/charging).
        if select_eid and flow:
            option = (
                self._opts.get(C.CONF_GRID_FLOW_DISCHARGE, C.DEFAULT_GRID_FLOW_DISCHARGE)
                if flow == "discharge"
                else self._opts.get(C.CONF_GRID_FLOW_CHARGE, C.DEFAULT_GRID_FLOW_CHARGE)
            )
            cur = self.hass.states.get(select_eid)
            if cur is None or cur.state != option:
                await self._call_select(select_eid, option)

        if number_eid:
            last = self._last_written
            changed_flow = last is None or last[0] != flow
            changed_power = last is None or abs(last[1] - power) >= deadband
            if changed_flow or changed_power or (power == 0.0 and (last is None or last[1] != 0.0)):
                await self._call_number(number_eid, power)
                self._last_written = (flow, power)

    async def _call_number(self, entity_id: str, value: float) -> None:
        try:
            await self.hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": entity_id, "value": round(value)},
                blocking=False,
            )
        except Exception as err:
            _LOGGER.error("number.set_value %s=%s failed: %s", entity_id, value, err)

    async def _call_select(self, entity_id: str, option: str) -> None:
        domain = entity_id.split(".", 1)[0]  # select | input_select
        try:
            await self.hass.services.async_call(
                domain, "select_option", {"entity_id": entity_id, "option": option}, blocking=False
            )
        except Exception as err:
            _LOGGER.error("select_option %s=%s failed: %s", entity_id, option, err)

    def _as_data(self, dec: logic.Decision) -> dict:
        return {
            C.KEY_ENABLED: self._enabled,
            C.KEY_MODE: dec.mode,
            C.KEY_TARGET_POWER: dec.target_power,
            C.KEY_DEMAND: dec.demand,
            C.KEY_SURPLUS: dec.surplus,
            "grid_flow": dec.grid_flow,
            "charge_release": dec.charge_release,
            "need_wh": dec.need_wh,
            "rest_pv_wh": dec.rest_pv_wh,
            "reason": dec.reason,
        }
