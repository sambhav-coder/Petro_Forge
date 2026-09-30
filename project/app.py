"""
FastAPI Microservice for SIH 2026 Problem Statement: SIH26120
Title: Digital Twin for Well-to-Surface Optimization of Cyclic Steam Stimulation (CSS) and Sucker Rod Pump (SRP) Operations for Heavy Oil Wells of Baghewala Field.
Sponsoring Organization: Oil India Limited
Domain: Heavy Oil / Baghewala Field - CSS + SRP Digital Twin

BLOCK 1: deterministic well-centric telemetry foundation.
Well -> Reservoir state -> Wellbore/production state -> CSS operating state -> SRP operating state.

BLOCK 2: deterministic engineering/physics foundation (twin_physics.py).
Transparent prototype thermal, viscosity, inflow, pump, SOR, energy and
engineering-indicator models. No ML, no optimization yet.

BLOCK 3: what-if simulation + joint CSSxSRP grid optimization
(twin_optimize.py) over the Block 2 physics. No ML. vfd_percent is
excluded from scenario/decision variables: no Block 2 physics function
consumes it (SPM is the SRP speed variable).

BLOCK 4: CSS cycle simulation + cut-off planning (css_cycle.py), synthetic
SRP dynamometer card (srp_dynacard.py), per-well history with twin
auto-calibration / anomaly detection / decline forecast (analytics.py),
failure-probability models trained on a documented synthetic hazard model
(ml.synthetic_hazard, canonical project/ml runtime, SYNTHETIC demo mode),
and real-time monitoring: live synthetic field
(live_field.py), Server-Sent Events stream, and alerts.

Explicitly NOT implemented: persistent database, auth, field control.
Nothing here issues commands to equipment.

Validation ranges below are INPUT-SAFETY ranges only. They are not
field-calibrated Baghewala limits.
"""

from collections import deque
from enum import Enum
import asyncio
import datetime
import hashlib
import json
import os

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Annotated, Any, Dict, List, Optional
import uvicorn

import analytics
import css_cycle
import live_field
from ml import synthetic_hazard  # canonical ML runtime (SYNTHETIC demo mode)
import srp_dynacard
import srp_performance
import twin_physics
import twin_optimize

from data import DATA_SCHEMA_VERSION, SYNTHETIC_GENERATOR_VERSION
from data import history as history_engine
from data.bootstrap import bootstrap_public_data
from data.pipeline import ingest_telemetry_batch
from data.provenance import ProvenanceClass
from data.repository import InMemoryRepository

# Priority 3: ML Intelligence Engine
try:
    from ml import (
        InferenceEngine,
        ModelRegistry,
        DatasetInventory,
        DatasetValidator,
        ExplainabilityEngine,
        get_provenance_tracker,
        MLEligibility,
        ModelTask,
        ModelStatus,
    )
    from ml.schemas import (
        PredictionRequest,
        PredictionResponse,
        DatasetValidationReport,
    )
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    # Create stubs for type hints
    InferenceEngine = None
    ModelRegistry = None
    DatasetInventory = None
    DatasetValidator = None
    ExplainabilityEngine = None
    get_provenance_tracker = None
    MLEligibility = None
    ModelTask = None
    ModelStatus = None
    PredictionRequest = None
    PredictionResponse = None
    DatasetValidationReport = None


APP_VERSION = "4.0.0-block4"

app = FastAPI(
    title="SIH26120 - Digital Twin for Well-to-Surface Optimization of Cyclic Steam Stimulation (CSS) and Sucker Rod Pump (SRP) Operations for Heavy Oil Wells of Baghewala Field.",
    description="Well-to-surface Digital Twin for Oil India Limited Baghewala heavy-oil wells (CSS + SRP). Block 3: what-if simulation and joint CSSxSRP optimization. Block 4: CSS cycle planning, SRP dynamometer card, predictive analytics, failure-probability models and real-time monitoring. Priority 2-3: historical time-series engine and ML Intelligence Engine with data validation, anomaly detection, and forecasting framework.",
    version=APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DOMAIN_LABEL = "Heavy Oil / Baghewala Field - CSS + SRP Digital Twin"


class CSSPhase(str, Enum):
    """Constrained CSS cycle phase. State machine only; no transition physics in Block 1."""

    INJECTION = "INJECTION"
    SOAK = "SOAK"
    PRODUCTION = "PRODUCTION"
    IDLE = "IDLE"


class WellTelemetry(BaseModel):
    """Domain-aware well telemetry/state record for one Baghewala well."""

    well_id: str = Field(..., min_length=1, max_length=64, json_schema_extra={"example": "BGW-01"})
    timestamp: Optional[str] = Field(
        default=None,
        description="ISO-8601 timestamp of the reading. Set by the server when omitted.",
    )

    # Reservoir / fluid state
    reservoir_temperature_c: float = Field(..., ge=0.0, le=350.0, json_schema_extra={"example": 47.0})
    reservoir_pressure_bar: float = Field(..., ge=0.0, le=500.0, json_schema_extra={"example": 28.5})
    api_gravity: float = Field(..., ge=5.0, le=50.0, json_schema_extra={"example": 18.0})

    # Wellbore / production state
    wellhead_pressure_bar: float = Field(..., ge=0.0, le=500.0, json_schema_extra={"example": 12.0})
    oil_rate_bopd: float = Field(..., ge=0.0, le=5000.0, json_schema_extra={"example": 22.5})

    # CSS operating state
    steam_volume_t: float = Field(..., ge=0.0, le=100000.0, json_schema_extra={"example": 850.0})
    steam_injection_pressure_bar: float = Field(..., ge=0.0, le=300.0, json_schema_extra={"example": 65.0})
    soak_time_h: float = Field(..., ge=0.0, le=720.0, json_schema_extra={"example": 48.0})
    css_phase: CSSPhase = Field(..., json_schema_extra={"example": "PRODUCTION"})

    # SRP operating state
    spm: float = Field(..., ge=0.0, le=20.0, json_schema_extra={"example": 5.0})
    stroke_in: float = Field(..., ge=0.0, le=300.0, json_schema_extra={"example": 96.0})
    vfd_percent: float = Field(..., ge=0.0, le=100.0, json_schema_extra={"example": 55.0})

    # Optional produced-fluids state
    water_cut_percent: float = Field(default=0.0, ge=0.0, le=100.0)

    # Optional elapsed time in the current CSS phase (drives production-phase cooling).
    days_in_phase: float = Field(default=0.0, ge=0.0, le=365.0)


class TelemetryIngestResponse(BaseModel):
    status: str
    event_id: str
    well_id: str
    timestamp: str
    sha256_hash: str
    well_state: WellTelemetry
    twin_summary: Optional["TwinSummaryResponse"] = None


class TwinSummaryResponse(BaseModel):
    """Concise engineering summary attached to ingest (Block 2)."""

    estimated_oil_production_bopd: float
    steam_oil_ratio_t_per_bbl: Optional[float] = None
    overall_engineering_status: str
    production_limiting_factor: str
    top_reason: str


class RiskIndicatorResponse(BaseModel):
    risk_level: str
    risk_score: float
    reason: str


class TwinSnapshotResponse(BaseModel):
    well_id: str
    timestamp: str
    css_phase: str
    heating_intensity: float
    baseline_reservoir_temperature_c: float
    estimated_temperature_c: float
    estimated_viscosity_cp: float
    mobility_factor: float
    reservoir_pressure_bar: float
    wellhead_pressure_bar: float
    drawdown_bar: float
    estimated_reservoir_inflow_bopd: float
    spm: float
    stroke_in: float
    pump_fillage: float
    pump_efficiency: float
    pump_theoretical_capacity_bopd: float
    pump_capacity_bopd: float
    estimated_oil_production_bopd: float
    estimated_liquid_production_bpd: float
    estimated_water_production_bwpd: float
    water_cut_percent: float
    estimated_pump_fillage: float
    vfd_setpoint_percent: float
    days_in_phase: float
    production_limiting_factor: str
    steam_volume_t: float
    evaluation_window_days: float
    estimated_oil_volume_bbl: float
    steam_oil_ratio_t_per_bbl: Optional[float] = None
    sor_status: str
    steam_energy_kwh: float
    pumping_energy_kwh: float
    total_energy_kwh: float
    energy_per_barrel_kwh: Optional[float] = None
    rod_float_risk: RiskIndicatorResponse
    impact_risk: RiskIndicatorResponse
    pump_unsetting_risk: RiskIndicatorResponse
    overall_engineering_status: str
    recommendation: str
    explanations: Dict[str, str]
    prototype_disclaimer: str


TelemetryIngestResponse.model_rebuild()


class ScenarioOverrides(BaseModel):
    """What-if overrides. Every field optional; omitted fields keep current values.

    vfd_percent is the drive setting that delivers SPM
    (twin_physics.spm_for_vfd). When given without spm it sets SPM; when
    both are given, spm wins and the VFD setpoint is re-derived from it.
    """

    steam_volume_t: Optional[float] = Field(default=None, ge=0.0, le=100000.0)
    steam_injection_pressure_bar: Optional[float] = Field(default=None, ge=0.0, le=300.0)
    soak_time_h: Optional[float] = Field(default=None, ge=0.0, le=720.0)
    spm: Optional[float] = Field(default=None, ge=0.0, le=20.0)
    stroke_in: Optional[float] = Field(default=None, ge=0.0, le=300.0)
    css_phase: Optional[CSSPhase] = None
    vfd_percent: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    water_cut_percent: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    days_in_phase: Optional[float] = Field(default=None, ge=0.0, le=365.0)


class ScenarioApplied(BaseModel):
    steam_volume_t: float
    steam_injection_pressure_bar: float
    soak_time_h: float
    spm: float
    stroke_in: float
    css_phase: str
    vfd_setpoint_percent: Optional[float] = None


class GridConfig(BaseModel):
    """Custom search grid: 1-5 values per dimension, all inside safety ranges."""

    steam_volume_t: List[Annotated[float, Field(ge=0.0, le=100000.0)]] = Field(min_length=1, max_length=5)
    steam_injection_pressure_bar: List[Annotated[float, Field(ge=0.0, le=300.0)]] = Field(min_length=1, max_length=5)
    soak_time_h: List[Annotated[float, Field(ge=0.0, le=720.0)]] = Field(min_length=1, max_length=5)
    spm: List[Annotated[float, Field(ge=0.0, le=20.0)]] = Field(min_length=1, max_length=5)
    stroke_in: List[Annotated[float, Field(ge=0.0, le=300.0)]] = Field(min_length=1, max_length=5)


class OptimizeRequest(BaseModel):
    search_grid: Optional[GridConfig] = None


class DeltaResponse(BaseModel):
    production_delta_bopd: float
    sor_delta_t_per_bbl: Optional[float] = None
    energy_delta_kwh: float
    status_from: str
    status_to: str
    status_changed: bool
    limiting_from: str
    limiting_to: str


class SimulateResponse(BaseModel):
    well_id: str
    mode: str
    scenario_inputs: ScenarioApplied
    current: "TwinSnapshotResponse"
    scenario: "TwinSnapshotResponse"
    delta: DeltaResponse
    prototype_disclaimer: str


class ScenarioResultResponse(BaseModel):
    rank: int
    inputs: ScenarioApplied
    estimated_oil_production_bopd: float
    steam_oil_ratio_t_per_bbl: Optional[float] = None
    sor_status: str
    total_energy_kwh: float
    energy_per_barrel_kwh: Optional[float] = None
    mean_risk: float = 0.0
    pareto_optimal: bool = False
    rod_float_risk: RiskIndicatorResponse
    impact_risk: RiskIndicatorResponse
    pump_unsetting_risk: RiskIndicatorResponse
    overall_engineering_status: str
    score: float


class RecommendedScenarioResponse(TwinSnapshotResponse):
    score: float
    inputs: ScenarioApplied


class OptimizeResponse(BaseModel):
    well_id: str
    mode: str
    current: "TwinSnapshotResponse"
    recommended: RecommendedScenarioResponse
    delta: DeltaResponse
    objective_score: float
    top_scenarios: List[ScenarioResultResponse]
    pareto_frontier: List[ScenarioResultResponse] = Field(default_factory=list)
    pareto_count: int = 0
    objective_summary: Dict[str, Any] = Field(default_factory=dict)
    constraints: List[Dict[str, Any]] = Field(default_factory=list)
    recommendation_policy: str = ""
    uncertainty_note: str = ""
    why_recommended: List[str]
    assumptions: List[str]
    scenarios_evaluated: int
    prototype_disclaimer: str


SimulateResponse.model_rebuild()
OptimizeResponse.model_rebuild()


class WellSummary(BaseModel):
    well_id: str
    last_update: Optional[str] = None
    css_phase: Optional[str] = None
    oil_rate_bopd: Optional[float] = None
    spm: Optional[float] = None
    stroke_in: Optional[float] = None
    provenance: str = "UNKNOWN"
    data_status: str = "LIVE_TELEMETRY"


class DispatchRequest(BaseModel):
    event_id: str
    protocol_type: str = Field(default="STANDARD_DISPATCH", json_schema_extra={"example": "HIGH_PRIORITY_ESCALATION"})
    notes: Optional[str] = None


class DispatchResponse(BaseModel):
    dispatch_id: str
    event_id: str
    status: str
    dispatched_at: str


# In-memory well state store: latest accepted telemetry per well_id.
# Restart persistence is intentionally out of scope for Block 1.
WELL_STORE: Dict[str, WellTelemetry] = {}

# Tamper-evident application audit log (in-memory, capped). This is a plain
# application hash per record, not a blockchain or chain-of-custody ledger.
AUDIT_LOGS: List[Dict] = []

# Deterministic monotonic counters (no randomness anywhere in Block 1).
_EVENT_SEQ = 0
_DISPATCH_SEQ = 0


def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _next_event_id() -> str:
    global _EVENT_SEQ
    _EVENT_SEQ += 1
    return f"EVT-{_EVENT_SEQ:06d}"


def _next_dispatch_id() -> str:
    global _DISPATCH_SEQ
    _DISPATCH_SEQ += 1
    return f"DISP-{_DISPATCH_SEQ:05d}"


def _telemetry_hash(well_id: str, event_id: str, timestamp: str, state: Dict) -> str:
    canonical = json.dumps(state, sort_keys=True, default=str)
    hash_str = f"{event_id}:SIH26120:{well_id}:{canonical}:{timestamp}"
    return hashlib.sha256(hash_str.encode()).hexdigest()


def _well_summary(well_id: str, record: WellTelemetry) -> Dict:
    phase = record.css_phase.value if hasattr(record.css_phase, "value") else str(record.css_phase)
    return {
        "well_id": well_id,
        "last_update": record.timestamp,
        "css_phase": phase,
        "oil_rate_bopd": record.oil_rate_bopd,
        "spm": record.spm,
        "stroke_in": record.stroke_in,
        "provenance": "UNKNOWN",
        "data_status": "LIVE_TELEMETRY",
    }


def _public_summary(pub: Dict[str, Any]) -> Dict:
    """List entry for a verified public well: NO telemetry fabricated."""
    return {
        "well_id": pub["well_id"],
        "last_update": None,
        "css_phase": None,
        "oil_rate_bopd": None,
        "spm": None,
        "stroke_in": None,
        "provenance": pub.get("provenance", "BAGHEWALA_FIELD"),
        "data_status": "PUBLIC_FIELD_RECORD",
    }


def _public_detail(well_id: str, pub: Dict[str, Any]) -> Dict:
    """Public-record envelope: historical/status data, telemetry null."""
    css = [c for c in PUBLIC_CSS if c.get("well_id") == well_id]
    prod = [p for p in PUBLIC_PROD_WELL if p.get("well_id") == well_id]
    return {
        "well_id": well_id,
        "data_status": "PUBLIC_FIELD_RECORD",
        "provenance": pub.get("provenance", "BAGHEWALA_FIELD"),
        "field": pub.get("field"),
        "reservoir": pub.get("reservoir"),
        "status": pub.get("status"),
        "status_as_of": pub.get("status_as_of"),
        "lift_method": pub.get("lift_method"),
        "css_status": pub.get("css_status"),
        "css_cycle_count": pub.get("css_cycle_count"),
        "css": css,
        "production": prod,
        "telemetry": None,
        "source_id": pub.get("source_id"),
        "confidence": pub.get("confidence"),
        "notes": pub.get("notes"),
    }


# ---------------- Block 4 stores (in-memory) ----------------
HISTORY_MAX = 720
HISTORY: Dict[str, deque] = {}          # per-well measured + twin time series
ALERTS: deque = deque(maxlen=200)       # newest last
_ACTIVE_ALERT_KEYS: Dict[tuple, str] = {}  # (well_id, type) -> alert_id while condition persists
_ALERT_SEQ = 0
_SUBSCRIBERS: List[asyncio.Queue] = []  # SSE listeners
LIVE: Dict[str, Any] = {"sim": None, "task": None, "interval_s": 2.0}

ML_ALERT_PROB = synthetic_hazard.PROB_HIGH


def reset_block1_state() -> None:
    """Test helper: clear in-memory wells, audit log, and deterministic counters."""
    global _EVENT_SEQ, _DISPATCH_SEQ, _ALERT_SEQ
    WELL_STORE.clear()
    AUDIT_LOGS.clear()
    _EVENT_SEQ = 0
    _DISPATCH_SEQ = 0
    HISTORY.clear()
    ALERTS.clear()
    _ACTIVE_ALERT_KEYS.clear()
    _ALERT_SEQ = 0
    _stop_live()
    LIVE["sim"] = None


def _broadcast(event: Dict) -> None:
    for q in list(_SUBSCRIBERS):
        try:
            q.put_nowait(event)
        except (asyncio.QueueFull, RuntimeError):
            pass  # slow or closed client: drop, it resyncs on the next event


def _raise_alert(well_id: str, ts: str, kind: str, severity: str, title: str, detail: str,
                 persistent: bool = True, extra: Optional[Dict] = None) -> Optional[Dict]:
    """Record an alert. Persistent conditions alert once until they clear."""
    global _ALERT_SEQ
    key = (well_id, kind)
    if persistent and key in _ACTIVE_ALERT_KEYS:
        return None
    _ALERT_SEQ += 1
    alert = {
        "alert_id": f"ALR-{_ALERT_SEQ:05d}", "well_id": well_id, "timestamp": ts,
        "type": kind, "severity": severity, "title": title, "detail": detail,
        "acknowledged": False, "active": persistent,
    }
    if extra:
        alert.update(extra)
    ALERTS.append(alert)
    if persistent:
        _ACTIVE_ALERT_KEYS[key] = alert["alert_id"]
    return alert


def _clear_alert(well_id: str, kind: str) -> None:
    alert_id = _ACTIVE_ALERT_KEYS.pop((well_id, kind), None)
    if alert_id:
        for a in ALERTS:
            if a["alert_id"] == alert_id:
                a["active"] = False


def _evaluate_alerts(state, snapshot: Dict, card: Dict, pred: Dict,
                     history: List[Dict], calib_k: Optional[float]) -> List[Dict]:
    """Condition checks after every reading. SRP/ML checks only while producing."""
    well, ts = state.well_id, state.timestamp
    producing = state.css_phase == CSSPhase.PRODUCTION
    raised = []

    def cond(kind, active, severity, title, detail, extra=None):
        if active:
            a = _raise_alert(well, ts, kind, severity, title, detail, extra=extra)
            if a:
                raised.append(a)
        else:
            _clear_alert(well, kind)

    cond("TWIN_HIGH_RISK", producing and snapshot["overall_engineering_status"] == "HIGH_RISK",
         "HIGH", "Engineering indicators HIGH", snapshot["recommendation"])
    high_diag = [d for d in card["diagnosis"] if d["severity"] == "HIGH"]
    cond("DYNACARD", producing and bool(high_diag), "HIGH",
         f"Dynacard: {high_diag[0]['code'].replace('_', ' ').title()}" if high_diag else "Dynacard",
         high_diag[0]["detail"] if high_diag else "")
    for name, p in pred["predictions"].items():
        cond(f"ML_{name.upper()}", producing and p["probability"] >= ML_ALERT_PROB, "HIGH",
             f"{name.replace('_', ' ').title()} risk {p['probability'] * 100:.0f}% (next {p['horizon_days']} d)",
             "Top drivers: " + ", ".join(
                 f"{d['label']} ({d['direction']})" for d in p["top_drivers"][:2]),
             extra={"model_mode": pred.get("mode", "SYNTHETIC")})
    # Anomalies on the newest reading; latched per metric so an ongoing fault alerts once.
    window = history[-(analytics.ANOMALY_WINDOW + 1):]
    newest = {(an["type"], an["metric"]): an
              for an in analytics.detect_anomalies(window, calib_k) if an["timestamp"] == ts}
    div = newest.get(("TWIN_DIVERGENCE", "oil_rate_bopd"))
    cond("TWIN_DIVERGENCE", div is not None, "MODERATE",
         "Measured oil diverges from calibrated twin", div["detail"] if div else "")
    for metric in analytics.ANOMALY_METRICS:
        out = newest.get(("STATISTICAL_OUTLIER", metric))
        cond(f"OUTLIER_{metric.upper()}", out is not None, "MODERATE",
             f"Abnormal {metric.replace('_', ' ')}", out["detail"] if out else "")
    return raised


def _ingest_state(payload, source: str = "API") -> Dict:
    """Single ingest path for API and live-field readings."""
    ts = payload.timestamp or _utc_now_iso()
    state = payload.model_copy(update={"timestamp": ts})

    WELL_STORE[state.well_id] = state

    event_id = _next_event_id()
    sha_hash = _telemetry_hash(state.well_id, event_id, ts, state.model_dump(mode="json"))

    AUDIT_LOGS.append(
        {
            "event_id": event_id,
            "ps_id": "SIH26120",
            "well_id": state.well_id,
            "css_phase": state.css_phase.value,
            "oil_rate_bopd": state.oil_rate_bopd,
            "sha256_hash": sha_hash,
            "timestamp": ts,
            "source": source,
        }
    )
    if len(AUDIT_LOGS) > 100:
        AUDIT_LOGS.pop(0)

    snapshot = twin_physics.twin_snapshot(state)
    card = srp_dynacard.dynacard(snapshot, state.api_gravity)
    pred = synthetic_hazard.predict(state)

    hist = HISTORY.setdefault(state.well_id, deque(maxlen=HISTORY_MAX))
    hist.append({
        "timestamp": ts,
        "css_phase": state.css_phase.value,
        "days_in_phase": state.days_in_phase,
        "oil_rate_bopd": state.oil_rate_bopd,
        "wellhead_pressure_bar": state.wellhead_pressure_bar,
        "reservoir_pressure_bar": state.reservoir_pressure_bar,
        "reservoir_temperature_c": state.reservoir_temperature_c,
        "spm": state.spm,
        "stroke_in": state.stroke_in,
        "vfd_percent": state.vfd_percent,
        "water_cut_percent": state.water_cut_percent,
        "steam_volume_t": state.steam_volume_t,
        "twin_oil_bopd": snapshot["estimated_oil_production_bopd"],
        "twin_temperature_c": snapshot["estimated_temperature_c"],
        "twin_viscosity_cp": snapshot["estimated_viscosity_cp"],
        "twin_status": snapshot["overall_engineering_status"],
        "pump_fillage": snapshot["estimated_pump_fillage"],
        "rod_failure_prob": pred["predictions"]["rod_failure"]["probability"],
        "pump_unsetting_prob": pred["predictions"]["pump_unsetting"]["probability"],
    })
    hist_list = list(hist)
    calib = analytics.calibrate(hist_list)
    alerts = _evaluate_alerts(state, snapshot, card, pred, hist_list,
                              calib["k"] if calib["status"] == "CALIBRATED" else None)

    _broadcast({
        "type": "reading", "source": source, "well_id": state.well_id, "timestamp": ts,
        "css_phase": state.css_phase.value, "oil_rate_bopd": state.oil_rate_bopd,
        "twin_oil_bopd": snapshot["estimated_oil_production_bopd"],
        "calibrated_twin_oil_bopd": round(calib["k"] * snapshot["estimated_oil_production_bopd"], 3),
        "overall_engineering_status": snapshot["overall_engineering_status"],
        "dynacard": card["primary_diagnosis"],
        "alerts": alerts,
    })
    return {"event_id": event_id, "sha": sha_hash, "state": state, "snapshot": snapshot}


@app.get("/", tags=["Health & Metadata"])
async def root():
    return {
        "problem_id": "SIH26120",
        "title": "Digital Twin for Well-to-Surface Optimization of Cyclic Steam Stimulation (CSS) and Sucker Rod Pump (SRP) Operations for Heavy Oil Wells of Baghewala Field.",
        "organization": "Oil India Limited",
        "department": "Oil India Limited",
        "theme": "Smart Automation",
        "domain": DOMAIN_LABEL,
        "subsystem": "Well-to-surface Digital Twin (Block 4: cycle planning, SRP diagnostics, predictive analytics, real-time monitoring)",
        "status": "OPERATIONAL",
        "version": APP_VERSION,
        "timestamp": _utc_now_iso(),
    }


@app.get("/api/v1/telemetry/stats", tags=["Telemetry"])
async def get_stats():
    """Deterministic well-centric statistics computed from WELL_STORE. No randomness."""
    total_wells = len(WELL_STORE)
    if total_wells == 0:
        return {
            "domain": DOMAIN_LABEL,
            "total_wells": 0,
            "active_wells": 0,
            "average_oil_rate_bopd": 0.0,
            "average_reservoir_temperature_c": 0.0,
            "average_wellhead_pressure_bar": 0.0,
            "system_health": "NO_DATA",
            "last_sync": _utc_now_iso(),
        }
    records = list(WELL_STORE.values())
    avg_oil = round(sum(r.oil_rate_bopd for r in records) / total_wells, 3)
    avg_temp = round(sum(r.reservoir_temperature_c for r in records) / total_wells, 3)
    avg_whp = round(sum(r.wellhead_pressure_bar for r in records) / total_wells, 3)
    last_sync = max(r.timestamp for r in records)
    return {
        "domain": DOMAIN_LABEL,
        "total_wells": total_wells,
        "active_wells": total_wells,
        "average_oil_rate_bopd": avg_oil,
        "average_reservoir_temperature_c": avg_temp,
        "average_wellhead_pressure_bar": avg_whp,
        "system_health": "OPERATIONAL",
        "last_sync": last_sync,
    }


@app.post(
    "/api/v1/telemetry/ingest",
    response_model=TelemetryIngestResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Telemetry"],
)
async def ingest_telemetry(payload: WellTelemetry):
    """Validate, store latest state for the well, and return the accepted state.

    Block 2 attaches a concise deterministic engineering summary computed
    by twin_physics. No ML, no risk scoring beyond transparent engineering
    indicators, no AI inference.

    Priority 2: also creates a historical observation snapshot.
    """
    res = _ingest_state(payload)
    state, snapshot, event_id, sha_hash = res["state"], res["snapshot"], res["event_id"], res["sha"]
    ts = state.timestamp

    # Priority 2: create historical observation snapshot (API ingests only; live
    # synthetic-field readings are kept out of the ML-safe history store).
    hist_obs = history_engine.HistoricalObservation(
        record_id=f"TEL-{state.well_id}-{event_id}",
        timestamp_start=ts,
        timestamp_end=ts,
        timestamp_precision=history_engine.TemporalPrecision.DATETIME,
        original_period=ts,
        approximate=False,
        well_id=state.well_id,
        scope=history_engine.ObservationScope.WELL,
        variable="oil_rate_bopd",
        value=state.oil_rate_bopd,
        unit="bopd",
        value_kind=history_engine.ValueKind.MEASURED,
        source_id="live_telemetry_ingest",
        provenance=history_engine.ProvenanceClass.UNKNOWN,
        data_status="LIVE_TELEMETRY",
        time_series_safe=True,
        ml_safe=True,
        data_quality="VALID",
        notes="Live telemetry snapshot created on ingest.",
    )
    _HISTORY_REPO.insert(hist_obs)

    summary = TwinSummaryResponse(
        estimated_oil_production_bopd=snapshot["estimated_oil_production_bopd"],
        steam_oil_ratio_t_per_bbl=snapshot["steam_oil_ratio_t_per_bbl"],
        overall_engineering_status=snapshot["overall_engineering_status"],
        production_limiting_factor=snapshot["production_limiting_factor"],
        top_reason=snapshot["recommendation"],
    )

    return TelemetryIngestResponse(
        status="TELEMETRY_ACCEPTED",
        event_id=event_id,
        well_id=state.well_id,
        timestamp=ts,
        sha256_hash=sha_hash,
        well_state=state,
        twin_summary=summary,
    )


# ---------------- Priority 1 recovery: public Baghewala bootstrap ----------------
# Verified public registry loads at startup so the twin never opens empty.
# 5 publicly verified well records (Baghewala field contains additional
# wells; only wells with sufficient publicly verifiable well-specific
# evidence are represented here). Telemetry wells (WELL_STORE) take
# precedence in merged views; public records are never upgraded into
# telemetry.
_PUBLIC_BOOT = bootstrap_public_data()
PUBLIC_WELLS: Dict[str, Dict[str, Any]] = _PUBLIC_BOOT["wells"]
PUBLIC_CSS: List[Dict[str, Any]] = _PUBLIC_BOOT["css"]
PUBLIC_PROD_WELL: List[Dict[str, Any]] = _PUBLIC_BOOT["production_well"]
PUBLIC_PROD_FIELD: List[Dict[str, Any]] = _PUBLIC_BOOT["production_field"]
PUBLIC_FIELD: Dict[str, Any] = _PUBLIC_BOOT["field"]
BOOTSTRAP_REPORT: Dict[str, Any] = _PUBLIC_BOOT["report"]


@app.get("/api/v1/wells", tags=["Wells"])
async def list_wells():
    """Merged well list: live telemetry wells + 5 publicly verified well records.

    Public entries carry null telemetry fields (never fabricated) and
    provenance BAGHEWALA_FIELD / data_status PUBLIC_FIELD_RECORD.
    """
    wells = [_well_summary(wid, rec) for wid, rec in sorted(WELL_STORE.items())]
    seen = set(WELL_STORE.keys())
    for wid in sorted(PUBLIC_WELLS.keys()):
        if wid not in seen:
            wells.append(_public_summary(PUBLIC_WELLS[wid]))
    return {"total_wells": len(wells), "wells": wells}


@app.get("/api/v1/wells/{well_id}", tags=["Wells"])
async def get_well(well_id: str):
    """Latest telemetry for ingested wells; public-record envelope for
    publicly verified well records without telemetry. 404 when unknown."""
    record = WELL_STORE.get(well_id)
    if record is not None:
        return record
    pub = PUBLIC_WELLS.get(well_id)
    if pub is not None:
        return _public_detail(well_id, pub)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Well '{well_id}' not found. No telemetry has been ingested for this well_id.",
    )


@app.get("/api/v1/wells/{well_id}/twin", response_model=TwinSnapshotResponse, tags=["Digital Twin"])
async def get_well_twin(well_id: str):
    """Deterministic engineering snapshot for the well's latest state."""
    record = WELL_STORE.get(well_id)
    if record is None:
        if well_id in PUBLIC_WELLS:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "INSUFFICIENT_PUBLIC_TELEMETRY",
                    "message": (
                        f"Well '{well_id}' is a verified public record "
                        "(PUBLIC_FIELD_RECORD) with no live telemetry: twin "
                        "snapshot unavailable. Load synthetic demo telemetry "
                        "to exercise the physics engine."
                    ),
                    "twin_data_status": "INSUFFICIENT_PUBLIC_TELEMETRY",
                    "provenance": "BAGHEWALA_FIELD",
                },
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Well '{well_id}' not found. No telemetry has been ingested for this well_id.",
        )
    return twin_physics.twin_snapshot(record)


def _applied_inputs(state) -> Dict:
    phase = state.css_phase.value if hasattr(state.css_phase, "value") else str(state.css_phase)
    return {
        "steam_volume_t": state.steam_volume_t,
        "steam_injection_pressure_bar": state.steam_injection_pressure_bar,
        "soak_time_h": state.soak_time_h,
        "spm": state.spm,
        "stroke_in": state.stroke_in,
        "css_phase": phase,
        "vfd_setpoint_percent": twin_physics.vfd_for_spm(state.spm),
    }


def _scenario_result(item: Dict) -> Dict:
    snap = item["snapshot"]
    return {
        "rank": item["rank"],
        "inputs": item["inputs"],
        "estimated_oil_production_bopd": snap["estimated_oil_production_bopd"],
        "steam_oil_ratio_t_per_bbl": snap["steam_oil_ratio_t_per_bbl"],
        "sor_status": snap["sor_status"],
        "total_energy_kwh": snap["total_energy_kwh"],
        "energy_per_barrel_kwh": snap["energy_per_barrel_kwh"],
        "mean_risk": item.get("mean_risk", 0.0),
        "pareto_optimal": item.get("pareto_optimal", False),
        "rod_float_risk": snap["rod_float_risk"],
        "impact_risk": snap["impact_risk"],
        "pump_unsetting_risk": snap["pump_unsetting_risk"],
        "overall_engineering_status": snap["overall_engineering_status"],
        "score": item["score"],
    }


@app.post("/api/v1/wells/{well_id}/simulate", response_model=SimulateResponse, tags=["Simulation"])
async def simulate_well(well_id: str, scenario: ScenarioOverrides):
    """Side-effect-free what-if simulation: current vs hypothetical scenario.

    WELL_STORE is never modified.
    """
    record = WELL_STORE.get(well_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Well '{well_id}' not found. No telemetry has been ingested for this well_id.",
        )
    overrides = scenario.model_dump(exclude_none=True)
    if "vfd_percent" in overrides and "spm" not in overrides:
        overrides["spm"] = twin_physics.spm_for_vfd(overrides["vfd_percent"])
    elif "spm" in overrides:
        overrides["vfd_percent"] = twin_physics.vfd_for_spm(overrides["spm"])
    hypo = twin_optimize.apply_scenario(record, overrides)
    current = twin_physics.twin_snapshot(record)
    projected = twin_physics.twin_snapshot(hypo)
    return SimulateResponse(
        well_id=well_id,
        mode=twin_optimize.SIM_MODE_LABEL,
        scenario_inputs=_applied_inputs(hypo),
        current=current,
        scenario=projected,
        delta=twin_optimize.compare_snapshots(current, projected),
        prototype_disclaimer=twin_physics.PROTOTYPE_DISCLAIMER,
    )


@app.post("/api/v1/wells/{well_id}/optimize", response_model=OptimizeResponse, tags=["Optimization"])
async def optimize_well(well_id: str, request: OptimizeRequest = None):
    """Joint CSSxSRP grid-search optimization over the Block 2 prototype physics.

    Side-effect free. Uses prototype demonstration weights (0.40 production,
    0.25 SOR, 0.15 energy, 0.20 risk) — not Oil India provided. Returns the
    Pareto frontier over (max production, min SOR, min per-barrel energy,
    min mean risk); the recommendation is the highest weighted score among
    non-dominated candidates. The result is a scenario recommendation,
    not a field command.
    """
    record = WELL_STORE.get(well_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Well '{well_id}' not found. No telemetry has been ingested for this well_id.",
        )
    grid = request.search_grid.model_dump() if request and request.search_grid else None
    try:
        result = twin_optimize.optimize_well(record, grid)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    best = result["best"]
    recommended = dict(best["snapshot"])
    recommended["score"] = best["score"]
    recommended["inputs"] = best["inputs"]
    return OptimizeResponse(
        well_id=well_id,
        mode=twin_optimize.OPT_MODE_LABEL,
        current=result["current"],
        recommended=recommended,
        delta=result["delta"],
        objective_score=best["score"],
        top_scenarios=[_scenario_result(item) for item in result["ranked"][: twin_optimize.TOP_K]],
        pareto_frontier=[_scenario_result(item) for item in result["frontier"]],
        pareto_count=result["pareto_count"],
        objective_summary=result["objective_summary"],
        constraints=result["constraints"],
        recommendation_policy=result["recommendation_policy"],
        uncertainty_note=result["uncertainty_note"],
        why_recommended=result["why_recommended"],
        assumptions=twin_optimize.assumption_lines(result["grid"]),
        scenarios_evaluated=result["scenarios_evaluated"],
        prototype_disclaimer=twin_physics.PROTOTYPE_DISCLAIMER,
    )


@app.get("/api/v1/audit/logs", tags=["Audit & Compliance"])
async def get_audit_logs():
    """Most recent telemetry-acceptance audit records with per-record SHA-256 hashes."""
    return {
        "total_records": len(AUDIT_LOGS),
        "records": AUDIT_LOGS[-20:],
    }


# ---------------- Priority 1: data foundation ----------------
# Canonical data store (in-memory runtime; JSONL/file backends available in
# data.repository for offline use). Existing telemetry endpoints unchanged.

DATA_REPO = InMemoryRepository()
DATA_QUALITY_LOG: List[str] = []  # quality statuses observed via /data/ingest

_CATALOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_catalog")


def _load_catalog_json(name: str) -> Any:
    path = os.path.join(_CATALOG_DIR, name)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


class DataIngestRequest(BaseModel):
    records: List[Dict[str, Any]] = Field(..., min_length=1, max_length=5000)
    source_id: str = Field(default="unspecified", min_length=1, max_length=128)
    provenance: ProvenanceClass = ProvenanceClass.UNKNOWN
    units: Optional[Dict[str, str]] = None


@app.get("/api/v1/data/sources", tags=["Data Foundation"])
async def data_sources():
    """Researched source registry (metadata/citations only)."""
    doc = _load_catalog_json("data_sources.json")
    sources = doc.get("sources", []) if isinstance(doc, dict) else []
    return {"version": doc.get("version", "1.0") if isinstance(doc, dict) else "1.0",
            "count": len(sources), "sources": sources}


@app.get("/api/v1/data/catalog", tags=["Data Foundation"])
async def data_catalog():
    """Dataset catalog incl. the honest telemetry-availability statement."""
    doc = _load_catalog_json("data_catalog.json")
    if not isinstance(doc, dict) or not doc:
        return {"version": "1.0", "datasets": [],
                "telemetry_availability_statement": "Catalog unavailable."}
    return doc


@app.get("/api/v1/data/coverage", tags=["Data Foundation"])
async def data_coverage():
    """Canonical public well-coverage matrix (5 publicly verified well records).

    Authoritative source: project/data/public/baghewala_well_coverage.json.
    Baghewala field contains additional wells; only wells with sufficient
    publicly verifiable well-specific evidence are represented here.
    """
    import os as _os
    path = _os.path.join(
        _os.path.dirname(_os.path.abspath(__file__)), "data", "public",
        "baghewala_well_coverage.json",
    )
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Coverage file unavailable.",
        )


@app.get("/api/v1/data/quality", tags=["Data Foundation"])
async def data_quality():
    """Aggregate quality-status counts observed by the ingestion pipeline."""
    by_status: Dict[str, int] = {}
    for s in DATA_QUALITY_LOG:
        by_status[s] = by_status.get(s, 0) + 1
    return {"total_ingested": len(DATA_QUALITY_LOG), "by_status": by_status}


@app.get("/api/v1/data/summary", tags=["Data Foundation"])
async def data_summary():
    """Store counts + provenance breakdown + public-registry status.

    Historical public records are reported as records, never as telemetry.
    """
    by_provenance: Dict[str, int] = {}
    for r in DATA_REPO.get_telemetry():
        key = str(r.provenance.value if hasattr(r.provenance, "value") else r.provenance)
        by_provenance[key] = by_provenance.get(key, 0) + 1
    sources = _load_catalog_json("data_sources.json")
    telemetry_ids = set(WELL_STORE.keys())
    return {
        "schema_version": DATA_SCHEMA_VERSION,
        "synthetic_generator_version": SYNTHETIC_GENERATOR_VERSION,
        "store": DATA_REPO.counts(),
        "by_provenance": by_provenance,
        "cataloged_sources": len(sources.get("sources", [])) if isinstance(sources, dict) else 0,
        "public_registry": {
            "public_wells": len(PUBLIC_WELLS),
            "public_css_records": len(PUBLIC_CSS),
            "public_production_records": len(PUBLIC_PROD_WELL) + len(PUBLIC_PROD_FIELD),
            "rejected_records": BOOTSTRAP_REPORT.get("rejected_records", 0),
            "coverage_valid": BOOTSTRAP_REPORT.get("coverage_valid", False),
            "coverage_file": "project/data/public/baghewala_well_coverage.json",
        },
        "data_status": {
            "public_field_records": len(PUBLIC_WELLS),
            "public_telemetry_records": 0,
            "synthetic_records": 0,
            "live_telemetry_wells": len(telemetry_ids),
        },
    }


@app.post("/api/v1/data/ingest", status_code=status.HTTP_201_CREATED, tags=["Data Foundation"])
async def data_ingest(payload: DataIngestRequest):
    """Validate + clean + store canonical telemetry records (JSON body only).

    No filesystem access, no uploads, no path handling — records arrive in
    the request body and pass through the deterministic pipeline.
    """
    report, _features = ingest_telemetry_batch(
        payload.records,
        DATA_REPO,
        source_id=payload.source_id,
        provenance=payload.provenance.value,
        units=payload.units,
        with_features=False,
    )
    DATA_QUALITY_LOG.extend(
        [k for k, v in report.quality_by_status.items() for _ in range(v)]
    )
    return report.to_dict()


# ---------------- Priority 2: historical / time-series engine ----------------
# Trustworthy historical foundation with temporal precision preservation,
# provenance isolation, and coverage-aware querying.

_HISTORY_REPO = history_engine.InMemoryHistoryRepository()
_HISTORY_BOOT = history_engine.build_public_history(_PUBLIC_BOOT)
_BOOT_REPORT = _HISTORY_REPO.bulk_insert(_HISTORY_BOOT)


class HistoryQueryParams(BaseModel):
    well_id: Optional[str] = None
    scope: Optional[str] = None
    variable: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    provenance: Optional[List[str]] = None
    precision: Optional[List[str]] = None
    include_derived: bool = False
    include_synthetic: bool = False
    include_live: bool = True
    limit: int = 100


@app.get("/api/v1/history", tags=["History"])
async def get_history(params: HistoryQueryParams = HistoryQueryParams()):
    """Query historical observations with safety defaults.

    Defaults exclude derived and synthetic data to prevent accidental mixing
    of provenance classes. Explicit filters required to include them.
    """
    obs = _HISTORY_REPO.query(
        well_id=params.well_id,
        scope=params.scope,
        variable=params.variable,
        start=params.start,
        end=params.end,
        provenance=params.provenance,
        precision=params.precision,
        include_derived=params.include_derived,
        include_synthetic=params.include_synthetic,
        include_live=params.include_live,
        limit=params.limit,
    )
    coverage = history_engine.compute_coverage(obs)
    return {
        "query": params.model_dump(exclude_none=True),
        "count": len(obs),
        "observations": [o.model_dump() for o in obs],
        "coverage": coverage,
        "metadata": {
            "include_derived": params.include_derived,
            "include_synthetic": params.include_synthetic,
            "include_live": params.include_live,
        },
    }


@app.get("/api/v1/history/wells/{well_id}", tags=["History"])
async def get_well_history(well_id: str, include_derived: bool = False,
                          include_synthetic: bool = False, include_live: bool = True,
                          variable: Optional[str] = None, limit: int = 100):
    """Historical observations for a specific well."""
    obs = _HISTORY_REPO.query(
        well_id=well_id,
        variable=variable,
        include_derived=include_derived,
        include_synthetic=include_synthetic,
        include_live=include_live,
        limit=limit,
    )
    coverage = history_engine.well_coverage_summary(_HISTORY_REPO, well_id)
    return {
        "well_id": well_id,
        "count": len(obs),
        "observations": [o.model_dump() for o in obs],
        "coverage": coverage,
    }


@app.get("/api/v1/history/field", tags=["History"])
async def get_field_history(include_derived: bool = False,
                             include_synthetic: bool = False, include_live: bool = True,
                             variable: Optional[str] = None, limit: int = 100):
    """Field-level historical observations."""
    obs = _HISTORY_REPO.query(
        scope="FIELD",
        variable=variable,
        include_derived=include_derived,
        include_synthetic=include_synthetic,
        include_live=include_live,
        limit=limit,
    )
    coverage = history_engine.compute_coverage(obs)
    return {
        "scope": "FIELD",
        "count": len(obs),
        "observations": [o.model_dump() for o in obs],
        "coverage": coverage,
    }


@app.get("/api/v1/history/coverage/{well_id}", tags=["History"])
async def get_well_coverage(well_id: str):
    """Coverage summary for a well (no observation details)."""
    return history_engine.well_coverage_summary(_HISTORY_REPO, well_id)


@app.get("/api/v1/history/trend/{well_id}", tags=["History"])
async def get_well_trend(well_id: str, variable: str,
                        include_derived: bool = False, include_synthetic: bool = False,
                        include_live: bool = True):
    """Trend analysis for a well's variable.

    Returns INSUFFICIENT for sparse series; never fabricates trends.
    """
    obs = _HISTORY_REPO.query(
        well_id=well_id,
        variable=variable,
        include_derived=include_derived,
        include_synthetic=include_synthetic,
        include_live=include_live,
        limit=1000,
    )
    return history_engine.analyze_trend(obs)


@app.get("/api/v1/history/aggregate", tags=["History"])
async def aggregate_history(operation: str, well_id: Optional[str] = None,
                           scope: Optional[str] = None, variable: Optional[str] = None,
                           include_derived: bool = False, include_synthetic: bool = False,
                           include_live: bool = True, limit: int = 100):
    """Safe aggregation over historical observations.

    Operations: count, min, max, mean, median, sum, latest, earliest.
    Refuses inappropriate aggregations with warnings.
    """
    obs = _HISTORY_REPO.query(
        well_id=well_id,
        scope=scope,
        variable=variable,
        include_derived=include_derived,
        include_synthetic=include_synthetic,
        include_live=include_live,
        limit=limit,
    )
    return history_engine.safe_aggregate(obs, operation)


@app.get("/api/v1/history/stats", tags=["History"])
async def get_history_stats():
    """Historical repository statistics."""
    return {
        "schema_version": history_engine.HISTORY_SCHEMA_VERSION,
        "repository": _HISTORY_REPO.counts(),
        "bootstrap": _BOOT_REPORT,
        "variable_registry": {
            name: {
                "label": spec.label,
                "unit": spec.unit,
                "domain": spec.domain,
                "kind": spec.kind.value,
                "chartable": spec.chartable,
                "ml_eligible": spec.ml_eligible,
            }
            for name, spec in history_engine.VARIABLE_REGISTRY.items()
        },
    }


# ---------------- Priority 3: ML Intelligence Engine ----------------
# ML API endpoints for forecasting, anomaly detection, SRP health, and failure prediction.

if ML_AVAILABLE:
    _ML_INFERENCE_ENGINE = InferenceEngine()
    _ML_REGISTRY = ModelRegistry()
    _ML_DATASET_INVENTORY = DatasetInventory()
    _ML_DATASET_VALIDATOR = DatasetValidator()
    _ML_EXPLAINABILITY_ENGINE = ExplainabilityEngine()
    _ML_PROVENANCE_TRACKER = get_provenance_tracker()
else:
    _ML_INFERENCE_ENGINE = None
    _ML_REGISTRY = None
    _ML_DATASET_INVENTORY = None
    _ML_DATASET_VALIDATOR = None
    _ML_EXPLAINABILITY_ENGINE = None
    _ML_PROVENANCE_TRACKER = None


class MLPredictionRequest(BaseModel):
    """ML prediction request."""
    task: str = Field(..., description="ML task: production_forecast, anomaly_detection, srp_health, failure_risk")
    well_id: Optional[str] = None
    features: Dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[str] = None
    model_id: Optional[str] = None
    model_version: Optional[str] = None
    return_explanations: bool = False


class MLForecastRequest(BaseModel):
    """Production forecast request."""
    well_id: str = Field(..., min_length=1)
    horizon_days: int = Field(default=30, ge=1, le=365)
    features: Dict[str, Any] = Field(default_factory=dict)
    model_id: Optional[str] = None
    model_version: Optional[str] = None


class MLAnomalyRequest(BaseModel):
    """Anomaly detection request."""
    variable: str = Field(..., min_length=1)
    value: float
    well_id: Optional[str] = None
    timestamp: Optional[str] = None
    historical_window: int = Field(default=30, ge=1, le=365)
    model_id: Optional[str] = None
    model_version: Optional[str] = None


class MLHealthRequest(BaseModel):
    """SRP health assessment request."""
    well_id: str = Field(..., min_length=1)
    features: Dict[str, Any] = Field(default_factory=dict)
    model_id: Optional[str] = None
    model_version: Optional[str] = None


class MLFailureRequest(BaseModel):
    """Failure prediction request."""
    well_id: str = Field(..., min_length=1)
    features: Dict[str, Any] = Field(default_factory=dict)
    model_id: Optional[str] = None
    model_version: Optional[str] = None


@app.get("/api/v1/ml/status", tags=["ML Intelligence"])
async def get_ml_status():
    """ML system status and available models."""
    if not ML_AVAILABLE:
        return {
            "status": "UNAVAILABLE",
            "version": "1.0",
            "available_models": {},
            "registry_summary": {},
            "datasets": 0,
            "timestamp": _utc_now_iso(),
            "reason": "ML module not available",
        }
    return {
        "status": "OPERATIONAL",
        "version": "1.0",
        "available_models": _ML_INFERENCE_ENGINE.get_available_models(),
        "registry_summary": _ML_REGISTRY.get_registry_summary(),
        "datasets": len(_ML_DATASET_INVENTORY.list_datasets()),
        "timestamp": _utc_now_iso(),
    }


@app.get("/api/v1/ml/models", tags=["ML Intelligence"])
async def list_ml_models(
    task: Optional[str] = None,
    status: Optional[str] = None,
):
    """List registered ML models with optional filtering."""
    if not ML_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML module not available",
        )
    models = _ML_REGISTRY.list_models(task=task, status=status)
    return {
        "total": len(models),
        "models": [m.model_dump() for m in models],
    }


@app.post("/api/v1/ml/predict", tags=["ML Intelligence"])
async def ml_predict(request: MLPredictionRequest):
    """Unified ML prediction endpoint.
    
    Routes to appropriate task-specific model based on request task.
    Returns explicit insufficient-data state when models are unavailable.
    """
    if not ML_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML module not available",
        )
    try:
        task = ModelTask(request.task)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid task: {request.task}. Valid tasks: {[t.value for t in ModelTask]}",
        )
    
    ml_request = PredictionRequest(
        task=task,
        well_id=request.well_id,
        features=request.features,
        timestamp=request.timestamp,
        model_id=request.model_id,
        model_version=request.model_version,
        return_explanations=request.return_explanations,
    )
    
    response = _ML_INFERENCE_ENGINE.predict(ml_request)
    return response


@app.post("/api/v1/ml/forecast", tags=["ML Intelligence"])
async def ml_forecast(request: MLForecastRequest):
    """Production forecasting endpoint.
    
    Returns explicit insufficient-data state when forecasting model unavailable.
    Baghewala public data is insufficient for continuous production forecasting.
    """
    if not ML_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML module not available",
        )
    response = _ML_INFERENCE_ENGINE.forecasting_model.forecast(
        well_id=request.well_id,
        features=request.features,
        model_id=request.model_id,
        model_version=request.model_version,
        horizon_days=request.horizon_days,
    )
    return response


@app.post("/api/v1/ml/anomaly", tags=["ML Intelligence"])
async def ml_anomaly(request: MLAnomalyRequest):
    """Anomaly detection endpoint.
    
    Detects anomalies in operational parameters using statistical methods.
    Returns explicit insufficient-data state when historical context unavailable.
    """
    if not ML_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML module not available",
        )
    response = _ML_INFERENCE_ENGINE.anomaly_detector.detect(
        variable=request.variable,
        value=request.value,
        well_id=request.well_id,
        timestamp=request.timestamp,
        model_id=request.model_id,
        model_version=request.model_version,
    )
    return response


@app.post("/api/v1/ml/srp-health", tags=["ML Intelligence"])
async def ml_srp_health(request: MLHealthRequest):
    """SRP/pump health assessment endpoint.
    
    Returns explicit insufficient-data state when SRP operational data unavailable.
    """
    if not ML_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML module not available",
        )
    response = _ML_INFERENCE_ENGINE.srp_health_model.assess(
        well_id=request.well_id,
        features=request.features,
        model_id=request.model_id,
        model_version=request.model_version,
    )
    return response


@app.post("/api/v1/ml/failure-risk", tags=["ML Intelligence"])
async def ml_failure_risk(request: MLFailureRequest):
    """Failure prediction endpoint.
    
    Returns explicit insufficient-data state when failure model unavailable.
    Baghewala public data lacks labeled failure data for training.
    """
    if not ML_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML module not available",
        )
    response = _ML_INFERENCE_ENGINE.failure_model.predict(
        well_id=request.well_id,
        features=request.features,
        model_id=request.model_id,
        model_version=request.model_version,
    )
    return response


@app.get("/api/v1/ml/datasets", tags=["ML Intelligence"])
async def list_ml_datasets():
    """List ML datasets and their eligibility."""
    if not ML_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML module not available",
        )
    datasets = _ML_DATASET_INVENTORY.list_datasets()
    return {
        "total": len(datasets),
        "datasets": [
            {
                "name": d.name,
                "source": d.source.value,
                "domain": d.domain,
                "rows": d.rows,
                "features": d.features,
                "time_information": d.time_information,
                "failure_labels": d.failure_labels,
            }
            for d in datasets
        ],
    }


@app.get("/api/v1/ml/datasets/{dataset_name}/eligibility", tags=["ML Intelligence"])
async def get_dataset_eligibility(dataset_name: str, task: str):
    """Get ML eligibility assessment for a dataset."""
    if not ML_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML module not available",
        )
    report = _ML_DATASET_INVENTORY.assess_eligibility(dataset_name, task)
    return report.model_dump()


@app.get("/api/v1/ml/models/{model_id}/explainability", tags=["ML Intelligence"])
async def get_model_explainability(model_id: str, top_k: int = 5):
    """Get feature importance for a model.
    
    Returns top contributing features and their importance scores.
    Distinguishes MODEL ASSOCIATION from PHYSICAL CAUSATION.
    """
    if not ML_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML module not available",
        )
    model = _ML_REGISTRY.get_model(model_id)
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{model_id}' not found",
        )
    
    # Note: This is a placeholder - actual implementation would need
    # the trained model object, not just metadata
    return {
        "model_id": model_id,
        "model_type": model.task,
        "feature_importance": [],
        "limitations": [
            "Feature importance requires trained model object",
            "Feature importance indicates association, not causation",
        ],
    }


@app.get("/api/v1/ml/provenance/summary", tags=["ML Intelligence"])
async def get_provenance_summary():
    """Get summary of ML provenance tracking."""
    if not ML_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML module not available",
        )
    return _ML_PROVENANCE_TRACKER.get_provenance_summary()


@app.get("/api/v1/ml/provenance/prediction/{prediction_id}", tags=["ML Intelligence"])
async def get_prediction_provenance(prediction_id: str):
    """Get full provenance for a specific prediction."""
    if not ML_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML module not available",
        )
    return _ML_PROVENANCE_TRACKER.export_provenance(prediction_id)


@app.get("/api/v1/ml/provenance/feature/{feature_name}", tags=["ML Intelligence"])
async def get_feature_lineage(feature_name: str):
    """Trace the lineage of a feature back to source columns."""
    if not ML_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML module not available",
        )
    lineage = _ML_PROVENANCE_TRACKER.trace_lineage(feature_name)
    return {
        "feature_name": feature_name,
        "lineage": [
            {
                "feature_name": prov.feature_name,
                "source_columns": prov.source_columns,
                "method": prov.method,
                "parameters": prov.parameters,
                "derived_from": prov.derived_from,
                "timestamp": prov.timestamp,
            }
            for prov in lineage
        ],
    }


@app.post("/api/v1/action/dispatch", response_model=DispatchResponse, tags=["Operations"])
async def dispatch_action(req: DispatchRequest):
    """Legacy dispatch acknowledgement (kept for backward compatibility).

    Does not issue field commands and is not connected to any equipment.
    """
    return DispatchResponse(
        dispatch_id=_next_dispatch_id(),
        event_id=req.event_id,
        status="DISPATCHED_TO_FIELD_TEAMS",
        dispatched_at=_utc_now_iso(),
    )


# =====================================================================
# BLOCK 4: cycle planning, SRP dynacard, analytics, ML, real-time
# =====================================================================

def _require_well(well_id: str) -> WellTelemetry:
    record = WELL_STORE.get(well_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Well '{well_id}' not found. No telemetry has been ingested for this well_id.",
        )
    return record


class CyclePlanRequest(BaseModel):
    steam_grid_t: Optional[List[Annotated[float, Field(ge=0.0, le=100000.0)]]] = Field(
        default=None, min_length=1, max_length=8)
    soak_grid_h: Optional[List[Annotated[float, Field(ge=0.0, le=720.0)]]] = Field(
        default=None, min_length=1, max_length=8)
    sor_limit_cwe: float = Field(default=css_cycle.SOR_CWE_LIMIT, gt=0.0, le=50.0)


class MultiCycleRequest(BaseModel):
    """Multi-cycle outlook request: sequential cycles with propagated state."""

    cycles: int = Field(default=3, ge=1, le=6)
    steam_grid_t: Optional[List[Annotated[float, Field(ge=0.0, le=100000.0)]]] = Field(
        default=None, min_length=1, max_length=8)
    soak_grid_h: Optional[List[Annotated[float, Field(ge=0.0, le=720.0)]]] = Field(
        default=None, min_length=1, max_length=8)
    sor_limit_cwe: float = Field(default=css_cycle.SOR_CWE_LIMIT, gt=0.0, le=50.0)


class LiveStartRequest(BaseModel):
    interval_s: float = Field(default=2.0, ge=0.2, le=60.0)
    hours_per_tick: float = Field(default=live_field.DEFAULT_HOURS_PER_TICK, ge=1.0, le=72.0)


class DemoSeedRequest(BaseModel):
    days: float = Field(default=45.0, ge=1.0, le=180.0)


@app.get("/api/v1/wells/{well_id}/cycle", tags=["CSS Cycle"])
async def well_cycle(well_id: str):
    """Day-by-day CSS cycle at the well's current settings + optimal production cut-off."""
    return css_cycle.simulate_cycle(_require_well(well_id))


@app.post("/api/v1/wells/{well_id}/cycle/plan", tags=["CSS Cycle"])
async def well_cycle_plan(well_id: str, request: Optional[CyclePlanRequest] = None):
    """Steam volume x soak time search, each at its own optimal cut-off, under an SOR ceiling."""
    req = request or CyclePlanRequest()
    return css_cycle.plan_cycle(_require_well(well_id), req.steam_grid_t, req.soak_grid_h,
                                req.sor_limit_cwe)


@app.post("/api/v1/wells/{well_id}/cycle/multi", tags=["CSS Cycle"])
async def well_cycle_multi(well_id: str, request: Optional[MultiCycleRequest] = None):
    """Sequential multi-cycle outlook with propagated reservoir state.

    Each cycle is planned on the state left by the previous cycle
    (pressure depletion + residual heat, prototype linkage), with
    cumulative oil/steam/SOR and a next-cycle recommendation. Historical
    CSS context is attached explicitly; sparse public records always
    report INSUFFICIENT_DATA for response calibration.
    """
    req = request or MultiCycleRequest()
    record = _require_well(well_id)
    hist_obs = _HISTORY_REPO.query(well_id=well_id, include_derived=True,
                                   include_synthetic=True, include_live=True,
                                   limit=1000)
    try:
        return css_cycle.simulate_multicycle(
            record, cycles=req.cycles, steam_grid=req.steam_grid_t,
            soak_grid=req.soak_grid_h, sor_limit=req.sor_limit_cwe,
            historical_observations=hist_obs)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@app.get("/api/v1/wells/{well_id}/dynacard", tags=["SRP Diagnostics"])
async def well_dynacard(well_id: str):
    """Predicted surface dynamometer card, rod loads and diagnosis for the latest state.

    Extended with pump performance (power, capacity, efficiency), structured
    screening diagnostics with tied actions, and separately-labeled canonical
    ML health evidence. All original dynacard fields are preserved.
    """
    record = _require_well(well_id)
    snap = twin_physics.twin_snapshot(record)
    card = srp_dynacard.dynacard(snap, record.api_gravity)
    ml_health = None
    if ML_AVAILABLE:
        try:
            ml_health = _ML_INFERENCE_ENGINE.srp_health_model.assess(
                well_id=well_id,
                features={"spm": record.spm, "stroke": record.stroke_in},
            ).model_dump()
        except Exception:
            ml_health = None
    card["pump_performance"] = srp_performance.performance_summary(snap, card, ml_health)
    return card


@app.get("/api/v1/wells/{well_id}/predict", tags=["Predictive Models"])
async def well_predict(well_id: str):
    """30-day rod-failure / pump-unsetting probabilities with feature attributions.

    Compatibility shim: routes to the canonical ml.synthetic_hazard runtime.
    Demonstration output (mode=SYNTHETIC), not field-validated intelligence.
    """
    return synthetic_hazard.predict(_require_well(well_id))


@app.get("/api/v1/ml/model", tags=["Predictive Models"])
async def ml_model_card():
    """Model card: training data statement, coefficients, holdout metrics.

    Compatibility shim over the canonical ml.synthetic_hazard runtime.
    """
    return synthetic_hazard.model_info()


@app.get("/api/v1/wells/{well_id}/history", tags=["Analytics"])
async def well_history(well_id: str, limit: int = Query(default=240, ge=1, le=HISTORY_MAX)):
    """Measured telemetry alongside the twin's prediction at each reading (oldest first)."""
    _require_well(well_id)
    points = list(HISTORY.get(well_id, []))[-limit:]
    return {"well_id": well_id, "count": len(points), "points": points}


@app.get("/api/v1/wells/{well_id}/analytics", tags=["Analytics"])
async def well_analytics(well_id: str):
    """Twin auto-calibration, anomalies and decline forecast from the well's history."""
    record = _require_well(well_id)
    result = analytics.analyze(list(HISTORY.get(well_id, [])))
    k = result["calibration"]["k"]
    snap = twin_physics.twin_snapshot(record)
    result["well_id"] = well_id
    result["calibrated_twin_oil_bopd"] = round(k * snap["estimated_oil_production_bopd"], 3)
    result["uncalibrated_twin_oil_bopd"] = snap["estimated_oil_production_bopd"]
    return result


@app.get("/api/v1/alerts", tags=["Real-time Monitoring"])
async def list_alerts(active_only: bool = False, well_id: Optional[str] = None,
                      limit: int = Query(default=50, ge=1, le=200)):
    """Newest-first alerts raised by twin, dynacard, ML and anomaly checks."""
    items = [a for a in reversed(ALERTS)
             if (not active_only or a["active"]) and (well_id is None or a["well_id"] == well_id)]
    unacked = sum(1 for a in ALERTS if not a["acknowledged"])
    return {"total": len(items), "unacknowledged": unacked, "alerts": items[:limit]}


@app.post("/api/v1/alerts/{alert_id}/ack", tags=["Real-time Monitoring"])
async def ack_alert(alert_id: str):
    for a in ALERTS:
        if a["alert_id"] == alert_id:
            a["acknowledged"] = True
            return a
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Alert '{alert_id}' not found.")


@app.get("/api/v1/field/overview", tags=["Real-time Monitoring"])
async def field_overview():
    """Field-level KPIs: measured vs calibrated-twin oil, phases, statuses, alerts."""
    wells = []
    for well_id, rec in sorted(WELL_STORE.items()):
        snap = twin_physics.twin_snapshot(rec)
        k = analytics.calibrate(list(HISTORY.get(well_id, [])))["k"]
        active = [a for a in ALERTS if a["well_id"] == well_id and a["active"]]
        wells.append({
            "well_id": well_id, "css_phase": rec.css_phase.value, "days_in_phase": rec.days_in_phase,
            "oil_rate_bopd": rec.oil_rate_bopd,
            "calibrated_twin_oil_bopd": round(k * snap["estimated_oil_production_bopd"], 3),
            "overall_engineering_status": snap["overall_engineering_status"],
            "active_alerts": len(active), "last_update": rec.timestamp,
        })
    producing = [w for w in wells if w["css_phase"] == "PRODUCTION"]
    by_phase: Dict[str, int] = {}
    for w in wells:
        by_phase[w["css_phase"]] = by_phase.get(w["css_phase"], 0) + 1
    return {
        "total_wells": len(wells),
        "producing_wells": len(producing),
        "by_phase": by_phase,
        "field_oil_rate_bopd": round(sum(w["oil_rate_bopd"] for w in producing), 3),
        "field_calibrated_twin_oil_bopd": round(sum(w["calibrated_twin_oil_bopd"] for w in producing), 3),
        "active_alerts": sum(1 for a in ALERTS if a["active"]),
        "unacknowledged_alerts": sum(1 for a in ALERTS if not a["acknowledged"]),
        "live": _live_status(),
        "wells": wells,
    }


# ---------------- Live synthetic field + SSE stream ----------------
def _live_status() -> Dict:
    sim = LIVE["sim"]
    task = LIVE["task"]
    return {
        "running": bool(task is not None and not task.done()),
        "interval_s": LIVE["interval_s"],
        "ticks": sim.ticks if sim else 0,
        "sim_clock": sim.clock.isoformat() if sim else None,
        "hours_per_tick": sim.hours_per_tick if sim else None,
        "wells": sim.well_ids() if sim else [],
        "provenance": "SYNTHETIC_BAGHEWALA",
    }


def _stop_live() -> None:
    task = LIVE.get("task")
    if task is not None and not task.done():
        task.cancel()
    LIVE["task"] = None


def _tick() -> List[Dict]:
    """Advance the synthetic field one step and ingest every well's reading."""
    if LIVE["sim"] is None:
        LIVE["sim"] = live_field.FieldSimulator()
    results = []
    for item in LIVE["sim"].step():
        res = _ingest_state(WellTelemetry(**item["reading"]), source="LIVE_SYNTHETIC")
        results.append({"well_id": res["state"].well_id, "event_id": res["event_id"],
                        "css_phase": res["state"].css_phase.value,
                        "fault_event": item["fault_event"], "cycle_no": item["cycle_no"]})
    return results


async def _live_loop() -> None:
    while True:
        _tick()
        await asyncio.sleep(LIVE["interval_s"])


@app.post("/api/v1/demo/seed", tags=["Real-time Monitoring"])
async def demo_seed(request: Optional[DemoSeedRequest] = None):
    """Backfill the synthetic Baghewala field with `days` of history (4 wells).

    Readings go through the normal ingest path (audit, twin, analytics, ML,
    alerts). Provenance: SYNTHETIC_BAGHEWALA — never field data.
    """
    req = request or DemoSeedRequest()
    if LIVE["sim"] is None:
        LIVE["sim"] = live_field.FieldSimulator()
    ticks = int(round(req.days * 24.0 / LIVE["sim"].hours_per_tick))
    faults = 0
    for _ in range(ticks):
        faults += sum(1 for r in _tick() if r["fault_event"])
    return {"status": "SEEDED", "ticks": ticks, "wells": LIVE["sim"].well_ids(),
            "readings": ticks * len(LIVE["sim"].wells), "fault_readings": faults,
            "alerts": len(ALERTS), "live": _live_status()}


@app.post("/api/v1/live/start", tags=["Real-time Monitoring"])
async def live_start(request: Optional[LiveStartRequest] = None):
    """Start streaming synthetic field readings every interval_s seconds."""
    req = request or LiveStartRequest()
    _stop_live()
    if LIVE["sim"] is None:
        LIVE["sim"] = live_field.FieldSimulator(hours_per_tick=req.hours_per_tick)
    LIVE["sim"].hours_per_tick = req.hours_per_tick
    LIVE["interval_s"] = req.interval_s
    LIVE["task"] = asyncio.get_running_loop().create_task(_live_loop())
    return _live_status()


@app.post("/api/v1/live/stop", tags=["Real-time Monitoring"])
async def live_stop():
    _stop_live()
    return _live_status()


@app.post("/api/v1/live/tick", tags=["Real-time Monitoring"])
async def live_tick():
    """Advance the synthetic field exactly one step (manual stepping for demos/tests)."""
    return {"readings": _tick(), "live": _live_status()}


@app.get("/api/v1/live/status", tags=["Real-time Monitoring"])
async def live_status():
    return _live_status()


def _sse(event: Dict) -> str:
    return f"event: {event.get('type', 'message')}\ndata: {json.dumps(event, default=str)}\n\n"


@app.get("/api/v1/stream", tags=["Real-time Monitoring"])
async def stream(request: Request, max_events: Optional[int] = Query(default=None, ge=1, le=10000)):
    """Server-Sent Events: a 'hello' field snapshot, then one 'reading' per ingest."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    _SUBSCRIBERS.append(queue)

    async def gen():
        sent = 0
        try:
            yield _sse({"type": "hello", "wells": sorted(WELL_STORE), "live": _live_status(),
                        "timestamp": _utc_now_iso()})
            sent += 1
            while max_events is None or sent < max_events:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield _sse(event)
                sent += 1
        finally:
            if queue in _SUBSCRIBERS:
                _SUBSCRIBERS.remove(queue)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
