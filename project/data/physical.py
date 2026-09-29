"""Physical validation (Priority 1, Part P).

Two tiers, kept strictly separate:
- HARD_SCHEMA_VALIDATION: physically impossible -> INVALID (reject).
- SOFT_PHYSICAL_WARNING: outside Baghewala-plausible windows -> WARNING.

Baghewala-plausible windows are SOFT because they are engineering
judgement, not field-calibrated limits. Only hard physics rejects.
"""

import math
from typing import List, Tuple

# field -> (hard_lo, hard_hi): violations are physically impossible.
HARD_BOUNDS = {
    "reservoir_temperature_c": (-50.0, 2000.0),
    "wellhead_temperature_c": (-50.0, 2000.0),
    "steam_injection_temperature_c": (0.0, 2000.0),
    "reservoir_pressure_bar": (0.0, 2000.0),
    "wellhead_pressure_bar": (0.0, 2000.0),
    "steam_injection_pressure_bar": (0.0, 2000.0),
    "pump_intake_pressure_bar": (0.0, 2000.0),
    "oil_rate_bopd": (0.0, 1_000_000.0),
    "steam_volume_t": (0.0, 10_000_000.0),
    "soak_time_h": (0.0, 100_000.0),
    "spm": (0.0, 100.0),
    "stroke_in": (0.0, 1000.0),
    "vfd": (0.0, 100.0),
    "pump_fillage": (0.0, 1.0),
    "pump_efficiency": (0.0, 1.0),
    "water_cut_fraction": (0.0, 1.0),
    "energy_kwh": (0.0, 1e12),
}

# field -> (soft_lo, soft_hi): outside -> WARNING, kept and flagged.
SOFT_BAGHEWALA_WINDOWS = {
    "reservoir_temperature_c": (20.0, 350.0),
    "reservoir_pressure_bar": (0.0, 300.0),
    "wellhead_pressure_bar": (0.0, 300.0),
    "steam_volume_t": (0.0, 100_000.0),
    "soak_time_h": (0.0, 720.0),
    "spm": (0.0, 20.0),
    "stroke_in": (0.0, 300.0),
    "oil_rate_bopd": (0.0, 5000.0),
}


def _finite(value: float) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def hard_check(field: str, value: float) -> Tuple[bool, str]:
    """Return (ok, reason). Non-finite or out of HARD_BOUNDS -> INVALID."""
    if not _finite(value):
        return False, f"{field}={value}: non-finite"
    bounds = HARD_BOUNDS.get(field)
    if bounds is None:
        return True, ""
    lo, hi = bounds
    if not (lo <= float(value) <= hi):
        return False, f"{field}={value}: outside hard bounds [{lo}, {hi}]"
    return True, ""


def soft_check(field: str, value: float) -> Tuple[bool, str]:
    """Return (ok, reason). Outside plausible window -> WARNING (kept)."""
    window = SOFT_BAGHEWALA_WINDOWS.get(field)
    if window is None or not _finite(value):
        return True, ""
    lo, hi = window
    if not (lo <= float(value) <= hi):
        return False, f"{field}={value}: outside Baghewala-plausible [{lo}, {hi}]"
    return True, ""


def validate_record(values: dict) -> Tuple[List[str], List[str], List[str]]:
    """Return (invalid_reasons, warning_reasons, info). Deterministic."""
    invalid: List[str] = []
    warnings: List[str] = []
    for field, value in values.items():
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        ok, reason = hard_check(field, float(value))
        if not ok:
            invalid.append(reason)
            continue
        ok_soft, reason_soft = soft_check(field, float(value))
        if not ok_soft:
            warnings.append(reason_soft)
    return invalid, warnings, []
