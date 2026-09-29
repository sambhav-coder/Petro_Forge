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

Explicitly NOT implemented in these blocks (see later blocks):
ML, failure-probability prediction, persistent database, auth,
frontend redesign, field control.

Validation ranges below are INPUT-SAFETY ranges only. They are not
field-calibrated Baghewala limits.
"""

from enum import Enum
import datetime
import hashlib
import json
import os

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Annotated, Any, Dict, List, Optional
import uvicorn

import twin_physics
import twin_optimize

from data import DATA_SCHEMA_VERSION, SYNTHETIC_GENERATOR_VERSION
from data.bootstrap import bootstrap_public_data
from data.pipeline import ingest_telemetry_batch
from data.provenance import ProvenanceClass
from data.repository import InMemoryRepository


app = FastAPI(
    title="SIH26120 - Digital Twin for Well-to-Surface Optimization of Cyclic Steam Stimulation (CSS) and Sucker Rod Pump (SRP) Operations for Heavy Oil Wells of Baghewala Field.",
    description="Well-to-surface Digital Twin for Oil India Limited Baghewala heavy-oil wells (CSS + SRP). Block 3: what-if simulation and joint CSSxSRP optimization over deterministic prototype physics.",
    version="3.2.0-block3",
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

    vfd_percent is intentionally absent: no Block 2 physics function
    consumes it, so exposing it would be a fake control.
    """

    steam_volume_t: Optional[float] = Field(default=None, ge=0.0, le=100000.0)
    steam_injection_pressure_bar: Optional[float] = Field(default=None, ge=0.0, le=300.0)
    soak_time_h: Optional[float] = Field(default=None, ge=0.0, le=720.0)
    spm: Optional[float] = Field(default=None, ge=0.0, le=20.0)
    stroke_in: Optional[float] = Field(default=None, ge=0.0, le=300.0)
    css_phase: Optional[CSSPhase] = None


class ScenarioApplied(BaseModel):
    steam_volume_t: float
    steam_injection_pressure_bar: float
    soak_time_h: float
    spm: float
    stroke_in: float
    css_phase: str


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


def reset_block1_state() -> None:
    """Test helper: clear in-memory wells, audit log, and deterministic counters."""
    global _EVENT_SEQ, _DISPATCH_SEQ
    WELL_STORE.clear()
    AUDIT_LOGS.clear()
    _EVENT_SEQ = 0
    _DISPATCH_SEQ = 0


@app.get("/", tags=["Health & Metadata"])
async def root():
    return {
        "problem_id": "SIH26120",
        "title": "Digital Twin for Well-to-Surface Optimization of Cyclic Steam Stimulation (CSS) and Sucker Rod Pump (SRP) Operations for Heavy Oil Wells of Baghewala Field.",
        "organization": "Oil India Limited",
        "department": "Oil India Limited",
        "theme": "Smart Automation",
        "domain": DOMAIN_LABEL,
        "subsystem": "Well-to-surface Digital Twin (Block 3: simulation + optimization)",
        "status": "OPERATIONAL",
        "version": "3.2.0-block3",
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
    """
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
        }
    )
    if len(AUDIT_LOGS) > 100:
        AUDIT_LOGS.pop(0)

    snapshot = twin_physics.twin_snapshot(state)
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
# Telemetry wells (WELL_STORE) take precedence in merged views; public
# records are never upgraded into telemetry.
_PUBLIC_BOOT = bootstrap_public_data()
PUBLIC_WELLS: Dict[str, Dict[str, Any]] = _PUBLIC_BOOT["wells"]
PUBLIC_CSS: List[Dict[str, Any]] = _PUBLIC_BOOT["css"]
PUBLIC_PROD_WELL: List[Dict[str, Any]] = _PUBLIC_BOOT["production_well"]
PUBLIC_PROD_FIELD: List[Dict[str, Any]] = _PUBLIC_BOOT["production_field"]
PUBLIC_FIELD: Dict[str, Any] = _PUBLIC_BOOT["field"]
BOOTSTRAP_REPORT: Dict[str, Any] = _PUBLIC_BOOT["report"]


@app.get("/api/v1/wells", tags=["Wells"])
async def list_wells():
    """Merged well list: live telemetry wells + verified public Baghewala wells.

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
    verified Baghewala wells without telemetry. 404 when unknown."""
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
    0.25 SOR, 0.15 energy, 0.20 risk) — not Oil India provided. The result
    is a scenario recommendation, not a field command.
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


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
