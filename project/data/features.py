"""Feature engineering foundation (Priority 1, Parts Q-R).

Every feature reuses twin_physics (never duplicated) and carries
origin + method + DERIVED_PROTOTYPE status for ML explainability.
"""

from typing import Callable, Dict, List, Optional

import twin_physics as tp

from .provenance import ProvenanceClass
from .schema import FeatureRecord, TelemetryRecord

DERIVED_PROTOTYPE = "DERIVED_PROTOTYPE"


def _feature(name: str, value: Optional[float], origin: str, method: str) -> FeatureRecord:
    return FeatureRecord(
        name=name,
        value=value,
        origin=origin,
        method=method,
        status=DERIVED_PROTOTYPE,
        provenance=ProvenanceClass.DERIVED,
    )


def heating_intensity_f(rec: TelemetryRecord) -> FeatureRecord:
    v = tp.heating_intensity(rec.steam_volume_t or 0.0, rec.steam_injection_pressure_bar or 0.0)
    return _feature("heating_intensity", v, "steam_volume_t,steam_injection_pressure_bar",
                    "twin_physics.heating_intensity")


def thermal_exposure_f(rec: TelemetryRecord) -> FeatureRecord:
    return _feature("thermal_exposure_h", rec.soak_time_h, "soak_time_h", "passthrough")


def estimated_viscosity_f(rec: TelemetryRecord, temperature_c: Optional[float] = None) -> FeatureRecord:
    t = temperature_c if temperature_c is not None else rec.reservoir_temperature_c
    if t is None:
        return _feature("estimated_viscosity_cp", None, "reservoir_temperature_c",
                        "twin_physics.viscosity_cp")
    v = tp.viscosity_cp(t, getattr(rec, "api_gravity", None) or tp.API_REF)
    # NOTE: TelemetryRecord carries no api_gravity; twin default used.
    return _feature("estimated_viscosity_cp", v, "reservoir_temperature_c",
                    "twin_physics.viscosity_cp")


def mobility_proxy_f(viscosity_cp: Optional[float]) -> FeatureRecord:
    if viscosity_cp is None:
        return _feature("mobility_proxy", None, "estimated_viscosity_cp",
                        "twin_physics.mobility_factor")
    return _feature("mobility_proxy", tp.mobility_factor(viscosity_cp),
                    "estimated_viscosity_cp", "twin_physics.mobility_factor")


def steam_to_oil_ratio_f(steam_t: Optional[float], oil_bbl: Optional[float]) -> FeatureRecord:
    if not steam_t or not oil_bbl or oil_bbl <= 0:
        return _feature("steam_to_oil_ratio", None, "steam_volume_t,oil_production_bbl",
                        "twin_physics.steam_oil_ratio")
    value, _ = tp.steam_oil_ratio(steam_t, oil_bbl)
    return _feature("steam_to_oil_ratio", value, "steam_volume_t,oil_production_bbl",
                    "twin_physics.steam_oil_ratio")


def pump_capacity_proxy_f(spm: Optional[float], stroke_in: Optional[float]) -> FeatureRecord:
    if spm is None or stroke_in is None:
        return _feature("pump_capacity_proxy_bopd", None, "spm,stroke_in",
                        "twin_physics.theoretical_pump_capacity_bopd")
    theo = tp.theoretical_pump_capacity_bopd(spm, stroke_in)
    return _feature("pump_capacity_proxy_bopd",
                    tp.actual_pump_capacity_bopd(theo), "spm,stroke_in",
                    "twin_physics.actual_pump_capacity_bopd")


def energy_per_barrel_f(total_kwh: Optional[float], production_bopd: Optional[float]) -> FeatureRecord:
    if not total_kwh or not production_bopd or production_bopd <= 0:
        return _feature("energy_per_barrel_kwh", None, "energy_kwh,oil_rate_bopd",
                        "division guarded (None at zero production)")
    return _feature("energy_per_barrel_kwh", total_kwh / production_bopd,
                    "energy_kwh,oil_rate_bopd", "division guarded (None at zero production)")


def delta_f(name: str, prev: Optional[float], curr: Optional[float], origin: str) -> FeatureRecord:
    if prev is None or curr is None:
        return _feature(name, None, origin, "curr_minus_prev")
    return _feature(name, curr - prev, origin, "curr_minus_prev")


SINGLE_RECORD_FEATURES: Dict[str, Callable[[TelemetryRecord], FeatureRecord]] = {
    "heating_intensity": heating_intensity_f,
    "thermal_exposure_h": thermal_exposure_f,
    "estimated_viscosity_cp": estimated_viscosity_f,
}

PAIRWISE_FEATURES = ("temperature_delta", "pressure_delta", "production_change",
                     "spm_change", "stroke_change", "vfd_change")


def engineer_pairwise(prev: TelemetryRecord, curr: TelemetryRecord) -> List[FeatureRecord]:
    mapping = {
        "temperature_delta": ("reservoir_temperature_c", prev.reservoir_temperature_c, curr.reservoir_temperature_c),
        "pressure_delta": ("reservoir_pressure_bar", prev.reservoir_pressure_bar, curr.reservoir_pressure_bar),
        "production_change": ("oil_rate_bopd", prev.oil_rate_bopd, curr.oil_rate_bopd),
        "spm_change": ("spm", prev.spm, curr.spm),
        "stroke_change": ("stroke_in", prev.stroke_in, curr.stroke_in),
        "vfd_change": ("vfd", prev.vfd, curr.vfd),
    }
    return [delta_f(name, p, c, origin) for name, (origin, p, c) in mapping.items()]


def engineer_record(rec: TelemetryRecord) -> List[FeatureRecord]:
    """Single-record features: physics reuse + capacity + SOR-window proxy."""
    out = [fn(rec) for fn in SINGLE_RECORD_FEATURES.values()]
    visc = next(f for f in out if f.name == "estimated_viscosity_cp").value
    out.append(mobility_proxy_f(visc))
    out.append(pump_capacity_proxy_f(rec.spm, rec.stroke_in))
    window_oil = (rec.oil_rate_bopd or 0.0) * tp.SOR_WINDOW_DAYS
    out.append(steam_to_oil_ratio_f(rec.steam_volume_t, window_oil if window_oil > 0 else None))
    out.append(energy_per_barrel_f(rec.energy_kwh, rec.oil_rate_bopd))
    return out
