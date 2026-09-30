"""SIH26120 Digital Twin — canonical Hybrid Twin workflow (P4).

Consolidates the existing engineering components into ONE explicit
well-to-surface workflow. No new physics, no duplicated equations, no new
ML system — every section reuses a canonical module:

  observed      live telemetry record (as ingested)
  physics       twin_physics.twin_snapshot (passed in, primary model)
  calibration   analytics.calibrate over per-well history (sufficient data only)
  divergence    measured vs calibrated-expected (else raw physics, flagged)
  diagnostics   srp_dynacard + srp_performance screening (non-confirmatory)
  ml_evidence   canonical synthetic-hazard result, kept SEPARATE (SYNTHETIC)
  recommend     evidence-mapped operator context (no prescriptions beyond
                what the underlying modules support)
  provenance    data-status / mode labels; uncertainty UNAVAILABLE (honest)

Physics is primary. ML never overrides physics. Insufficient data yields
explicit INSUFFICIENT_DATA / UNAVAILABLE states, never invented results.
"""

from typing import Any, Dict, List, Optional

import analytics
import srp_dynacard as dc
import srp_performance as perf
import twin_physics as tp
from data.history import SYNTHETIC_WELL_IDS
from ml import synthetic_hazard

HYBRID_MODE = "HYBRID_PROTOTYPE_TWIN"
PHYSICS_MODE = "PROTOTYPE_PHYSICS"
UNCERTAINTY_STATUS = "UNAVAILABLE"
DIVERGENCE_HIGH_FRAC = 0.5   # matches analytics.DIVERGENCE_FRAC
DIVERGENCE_WATCH_FRAC = 0.2  # [PROTO] screening band below the divergence flag


def _observed_state(well_id: str, record) -> Dict[str, Any]:
    get = (lambda k, d=None: record.get(k, d)) if isinstance(record, dict) \
        else (lambda k, d=None: getattr(record, k, d))
    phase = get("css_phase")
    phase = phase.value if hasattr(phase, "value") else str(phase)
    synthetic = well_id in SYNTHETIC_WELL_IDS
    return {
        "well_id": well_id,
        "timestamp": get("timestamp"),
        "css_phase": phase,
        "oil_rate_bopd": get("oil_rate_bopd"),
        "reservoir_temperature_c": get("reservoir_temperature_c"),
        "reservoir_pressure_bar": get("reservoir_pressure_bar"),
        "wellhead_pressure_bar": get("wellhead_pressure_bar"),
        "steam_volume_t": get("steam_volume_t"),
        "steam_injection_pressure_bar": get("steam_injection_pressure_bar"),
        "soak_time_h": get("soak_time_h"),
        "spm": get("spm"),
        "stroke_in": get("stroke_in"),
        "vfd_percent": get("vfd_percent"),
        "water_cut_percent": get("water_cut_percent", 0.0),
        "data_status": "SYNTHETIC_DEMO" if synthetic else "LIVE_TELEMETRY",
        "provenance": "SYNTHETIC_BAGHEWALA" if synthetic else "UNKNOWN",
    }


def _calibration_block(history: List[Dict]) -> Dict[str, Any]:
    calib = analytics.calibrate(history)
    if calib["status"] != "CALIBRATED":
        return {"status": "INSUFFICIENT_DATA",
                "factor": None, "observations": calib.get("points", 0),
                "r2": None, "mape_percent": None,
                "explanation": calib.get("explanation", "")}
    return {"status": "CALIBRATED",
            "factor": calib["k"], "observations": calib["points"],
            "outliers_excluded": calib.get("outliers_excluded", 0),
            "r2": calib.get("r2"), "mape_percent": calib.get("mape_percent"),
            "explanation": calib.get("explanation", "")}


def _divergence_block(history: List[Dict], calibration: Dict,
                      snapshot: Dict) -> Dict[str, Any]:
    prod = [h for h in history if h.get("css_phase") == "PRODUCTION"
            and h.get("twin_oil_bopd", 0) > 0]
    if not prod:
        return {"status": "UNAVAILABLE", "value_bopd": None,
                "relative": None, "severity": None, "baseline": None,
                "note": "No production history points: divergence cannot be computed."}
    latest = prod[-1]
    measured = float(latest["oil_rate_bopd"])
    if calibration["status"] == "CALIBRATED":
        expected = float(calibration["factor"]) * float(latest["twin_oil_bopd"])
        baseline = "calibrated"
    else:
        expected = float(latest["twin_oil_bopd"])
        baseline = "raw_physics"
    if expected <= 0:
        return {"status": "UNAVAILABLE", "value_bopd": None,
                "relative": None, "severity": None, "baseline": baseline,
                "note": "Non-positive twin expectation: residual undefined."}
    rel = abs(measured - expected) / expected
    severity = ("DIVERGED" if rel > DIVERGENCE_HIGH_FRAC
                else "WATCH" if rel > DIVERGENCE_WATCH_FRAC else "TRACKING")
    return {"status": "CALCULATED",
            "value_bopd": round(measured - expected, 3),
            "relative": round(rel, 4), "severity": severity,
            "baseline": baseline, "timestamp": latest.get("timestamp"),
            "note": ("Measured vs " + ("calibrated twin (k=%.3f)" % calibration["factor"]
                    if baseline == "calibrated" else "raw prototype physics (twin uncalibrated)") + ".")}


def _recommendations(divergence: Dict, diagnostics: List[Dict],
                     calibration: Dict, snapshot: Dict) -> List[Dict[str, str]]:
    recs: List[Dict[str, str]] = []
    if divergence.get("severity") == "DIVERGED":
        recs.append({"source": "divergence", "severity": "MODERATE",
                     "text": ("Measured production diverges from the twin: investigate "
                              "model/data mismatch (sensor, pump wear, or a real reservoir "
                              "change) before trusting projections.")})
    for d in diagnostics:
        if d["code"] == "NORMAL_OPERATION":
            continue
        for action in d["recommended_actions"][:2]:
            recs.append({"source": d["code"], "severity": d["severity"],
                         "text": action})
        if len(recs) >= 4:
            break
    if calibration["status"] != "CALIBRATED":
        recs.append({"source": "calibration", "severity": "LOW",
                     "text": ("Calibration needs %d+ production readings: keep recording "
                              "telemetry; projections use raw prototype physics until then."
                              % analytics.CALIB_MIN_POINTS)})
    if not recs:
        recs.append({"source": "twin", "severity": "LOW",
                     "text": ("Twin tracking nominally: maintain current operating point "
                              "and continue routine surveillance.")})
    return recs[:5]


def build_hybrid_twin(well_id: str, record, snapshot: Dict,
                      history: List[Dict],
                      ml_result: Optional[Dict] = None) -> Dict[str, Any]:
    """Assemble the canonical Hybrid Twin view. Pure assembly over canonical
    modules; deterministic for identical inputs."""
    observed = _observed_state(well_id, record)
    calibration = _calibration_block(history)
    divergence = _divergence_block(history, calibration, snapshot)

    card = dc.dynacard(snapshot, float(getattr(record, "api_gravity", 18.0)
                                      if not isinstance(record, dict)
                                      else record.get("api_gravity", 18.0)))
    eff = perf.pump_efficiency(
        snapshot.get("estimated_liquid_production_bpd"),
        snapshot.get("pump_theoretical_capacity_bopd"))
    diagnostics = perf.diagnose_loading(card, snapshot, eff)

    if ml_result is None:
        ml_result = synthetic_hazard.predict(record)
    ml_evidence = {
        "status": "ATTACHED_SEPARATE_EVIDENCE",
        "mode": ml_result.get("mode", "SYNTHETIC"),
        "training_data": ml_result.get("training_data", "synthetic"),
        "production_safe": ml_result.get("production_safe", False),
        "predictions": ml_result.get("predictions", {}),
        "note": ("Canonical synthetic-hazard risk is separate supporting evidence: "
                 "demonstration output, never merged into the physics prediction."),
    }

    physics = {
        "status": "CALCULATED",
        "mode": PHYSICS_MODE,
        "prediction": {
            "oil_production_bopd": snapshot.get("estimated_oil_production_bopd"),
            "reservoir_inflow_bopd": snapshot.get("estimated_reservoir_inflow_bopd"),
            "pump_capacity_bopd": snapshot.get("pump_capacity_bopd"),
            "limiting_factor": snapshot.get("production_limiting_factor"),
            "temperature_c": snapshot.get("estimated_temperature_c"),
            "viscosity_cp": snapshot.get("estimated_viscosity_cp"),
            "mobility_factor": snapshot.get("mobility_factor"),
            "steam_oil_ratio_t_per_bbl": snapshot.get("steam_oil_ratio_t_per_bbl"),
            "total_energy_kwh": snapshot.get("total_energy_kwh"),
            "engineering_status": snapshot.get("overall_engineering_status"),
        },
    }
    calibrated_prediction = None
    if calibration["status"] == "CALIBRATED":
        calibrated_prediction = {
            "oil_production_bopd": round(
                float(calibration["factor"])
                * float(snapshot.get("estimated_oil_production_bopd", 0.0)), 3),
            "factor": calibration["factor"],
            "note": "Calibrated twin = factor x raw physics (physics shape, field magnitude).",
        }

    return {
        "well_id": well_id,
        "mode": HYBRID_MODE,
        "data_status": observed["data_status"],
        "observed": observed,
        "physics": physics,
        "calibration": calibration,
        "calibrated_prediction": calibrated_prediction,
        "divergence": divergence,
        "diagnostics": diagnostics,
        "ml_evidence": ml_evidence,
        "recommendations": _recommendations(divergence, diagnostics, calibration, snapshot),
        "provenance": {
            "data_status": observed["data_status"],
            "observed_provenance": observed["provenance"],
            "physics_mode": PHYSICS_MODE,
            "ml_mode": ml_evidence["mode"],
            "note": ("Public Baghewala records are sparse historical evidence, never live "
                     "telemetry; synthetic/demo telemetry is labeled and never presented "
                     "as field measurements."),
        },
        "uncertainty": {
            "status": UNCERTAINTY_STATUS,
            "note": "Uncertainty quantification is unavailable: deterministic point "
                    "evaluations only; no confidence bands are computed or implied.",
        },
        "prototype_disclaimer": tp.PROTOTYPE_DISCLAIMER,
    }
