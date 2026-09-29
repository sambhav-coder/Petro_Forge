"""Canonical units + normalization (Priority 1, Part N).

Canonical: temperature °C, pressure bar, oil rate BOPD, steam tonnes,
time hours, stroke inches, SPM strokes/min, VFD percent, energy kWh,
viscosity cP, water cut fraction 0-1.

Ambiguous units are NEVER silently converted: the value passes through
unchanged with an ambiguity flag + validation warning.
"""

from typing import Optional, Tuple

# field -> (canonical_unit, {accepted_unit: factor_to_canonical})
_CONVERSIONS = {
    "temperature": ("C", {"C": 1.0, "celsius": 1.0, "F": "f_to_c", "fahrenheit": "f_to_c", "K": "k_to_c"}),
    "pressure": ("bar", {"bar": 1.0, "psi": 0.0689476, "kPa": 0.01, "MPa": 10.0}),
    "oil_rate": ("BOPD", {"BOPD": 1.0, "bopd": 1.0, "bbl/d": 1.0, "m3/d": 6.28981}),
    "steam_volume": ("t", {"t": 1.0, "tonnes": 1.0, "kg": 0.001, "kt": 1000.0}),
    "time_h": ("h", {"h": 1.0, "hours": 1.0, "min": 1.0 / 60.0, "days": 24.0}),
    "stroke": ("in", {"in": 1.0, "inches": 1.0, "cm": 0.393701, "mm": 0.0393701}),
    "energy": ("kWh", {"kWh": 1.0, "MWh": 1000.0, "J": 1.0 / 3_600_000.0}),
    "viscosity": ("cP", {"cP": 1.0, "cp": 1.0, "mPa.s": 1.0, "Pa.s": 1000.0}),
}

# TelemetryRecord field -> conversion family (None = unitless / handled elsewhere).
FIELD_FAMILY = {
    "reservoir_temperature_c": "temperature",
    "wellhead_temperature_c": "temperature",
    "steam_injection_temperature_c": "temperature",
    "reservoir_pressure_bar": "pressure",
    "wellhead_pressure_bar": "pressure",
    "steam_injection_pressure_bar": "pressure",
    "pump_intake_pressure_bar": "pressure",
    "oil_rate_bopd": "oil_rate",
    "steam_volume_t": "steam_volume",
    "soak_time_h": "time_h",
    "stroke_in": "stroke",
    "energy_kwh": "energy",
}


def normalize_value(family: str, value: float, unit: Optional[str]) -> Tuple[float, Optional[str]]:
    """Return (canonical_value, warning_or_None).

    Unknown/ambiguous unit -> value passes through unchanged + warning flag.
    VFD-like and water-cut fields are intentionally NOT auto-converted here.
    """
    table = _CONVERSIONS.get(family)
    if table is None:
        return value, "unknown_family"
    canonical, factors = table
    if unit is None or unit == "":
        return value, "unit_assumed_canonical:" + canonical
    factor = factors.get(unit)
    if factor is None:
        return value, "ambiguous_unit:" + str(unit)
    if factor == "f_to_c":
        return (value - 32.0) * 5.0 / 9.0, None
    if factor == "k_to_c":
        return value - 273.15, None
    return value * float(factor), None


def normalize_water_cut(value: float, unit: Optional[str]) -> Tuple[float, Optional[str]]:
    """Canonical water cut is a fraction in [0, 1]. Percent needs explicit unit."""
    if unit in ("fraction", "frac", None, ""):
        if value > 1.0:
            return value, "ambiguous_unit:expected_fraction_got_" + str(value)
        return value, None
    if unit in ("percent", "%", "pct"):
        return value / 100.0, None
    return value, "ambiguous_unit:" + str(unit)


def normalize_vfd(value: float, unit: Optional[str]) -> Tuple[float, Optional[str]]:
    """VFD percent is canonical; Hz or other units are ambiguous by design."""
    if unit in ("percent", "%", None, ""):
        return value, None
    return value, "ambiguous_unit:" + str(unit)
