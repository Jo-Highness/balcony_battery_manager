"""Unit normalisation for the measurement and actuator entities (no HA imports).

All control logic works in watts (power), percent (state of charge) and kWh
(capacity). Sensors may report other units (e.g. kW); reading such a sensor as
watts would be off by a factor of 1000, so every value is converted here. An
unknown unit returns ``None`` and the caller treats the sensor as unavailable
(fail-safe) instead of guessing.
"""

from __future__ import annotations

# factor to convert a value in <unit> into the base unit
POWER_TO_W: dict[str, float] = {"mW": 0.001, "W": 1.0, "kW": 1000.0, "MW": 1_000_000.0}
ENERGY_TO_KWH: dict[str, float] = {"Wh": 0.001, "kWh": 1.0, "MWh": 1000.0}
PERCENT: dict[str, float] = {"%": 1.0}


def factor(unit: str | None, table: dict[str, float]) -> float | None:
    """Return the conversion factor for ``unit`` into the table's base unit.

    A missing unit (``None`` / empty) is assumed to already be in the base unit
    (helpers and template sensors often carry no unit). Returns ``None`` for a
    unit the table does not know.
    """
    if unit is None or unit == "":
        return 1.0
    return table.get(unit)


def convert(value: float, unit: str | None, table: dict[str, float]) -> float | None:
    """Convert ``value`` given in ``unit`` into the table's base unit (or None)."""
    f = factor(unit, table)
    return None if f is None else value * f
