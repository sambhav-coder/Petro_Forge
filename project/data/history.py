"""Historical / time-series engine (Priority 2).

Trustworthy historical foundation: actual public observations, field vs well
separation, temporal-precision preservation, provenance isolation, coverage /
aggregation / trend-gap analysis. No interpolation is ever fabricated: sparse
points stay sparse, and single-point series report INSUFFICIENT coverage.

Migration path: HistoricalRepository is an interface; the file-backed
JsonlHistoryRepository can later be replaced by a TimescaleDB/PostgreSQL
implementation without API changes.
"""

import calendar
import json
import os
import re
from abc import ABC, abstractmethod
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from .provenance import ProvenanceClass
from .repository import safe_base_dir

HISTORY_SCHEMA_VERSION = "1.0"

# Trend policy: minimum observations + required precision for a trend claim.
MIN_OBSERVATIONS_FOR_TREND = 2
TREND_ELIGIBLE_PRECISION = {"DAY", "DATETIME"}

# Well ids reserved for synthetic/demo telemetry (never public history).
SYNTHETIC_WELL_IDS = {"BGW-DEMO", "BGW-S01", "BGW-S02", "BGW-S03"}


class TemporalPrecision(str, Enum):
    YEAR = "YEAR"
    FINANCIAL_YEAR = "FINANCIAL_YEAR"
    MONTH = "MONTH"
    DAY = "DAY"
    DATETIME = "DATETIME"
    RANGE = "RANGE"
    APPROXIMATE = "APPROXIMATE"


class ObservationScope(str, Enum):
    FIELD = "FIELD"
    WELL = "WELL"


class ValueKind(str, Enum):
    MEASURED = "measured"
    REPORTED = "reported"
    REPORTED_RANGE = "reported_range"
    DERIVED_MIDPOINT = "derived_midpoint"
    LOWER_BOUND = "lower_bound"
    EVENT = "event"
    STATUS = "status"


class VariableKind(str, Enum):
    RATE = "rate"                    # per-day rate: mean ok, sum forbidden
    INSTANTANEOUS = "instantaneous"  # point reading: mean ok, sum forbidden
    CUMULATIVE = "cumulative"        # volume/energy: sum ok
    EVENT = "event"                  # occurrence: count only
    CATEGORICAL = "categorical"      # label: count only


class VariableSpec(BaseModel):
    name: str
    label: str
    unit: str
    domain: str
    scopes: List[str] = Field(default_factory=lambda: ["FIELD", "WELL"])
    kind: VariableKind = VariableKind.INSTANTANEOUS
    chartable: bool = True
    ml_eligible: bool = False


def _v(name: str, label: str, unit: str, domain: str,
       kind: VariableKind = VariableKind.INSTANTANEOUS,
       scopes: Optional[List[str]] = None,
       chartable: bool = True, ml_eligible: bool = False) -> VariableSpec:
    return VariableSpec(
        name=name, label=label, unit=unit, domain=domain, kind=kind,
        scopes=scopes or ["FIELD", "WELL"],
        chartable=chartable, ml_eligible=ml_eligible,
    )


# Controlled variable registry (Phase 2). No values live here — metadata only.
VARIABLE_REGISTRY: Dict[str, VariableSpec] = {}
for _spec in [
    _v("reservoir_temperature_c", "Reservoir temperature", "C", "RESERVOIR"),
    _v("reservoir_pressure_bar", "Reservoir pressure", "bar", "RESERVOIR"),
    _v("viscosity_cp", "Oil viscosity", "cP", "RESERVOIR"),
    _v("oil_rate_bopd", "Oil rate", "bopd", "PRODUCTION", VariableKind.RATE,
       ml_eligible=True),
    _v("water_cut_percent", "Water cut", "%", "PRODUCTION", VariableKind.INSTANTANEOUS,
       ml_eligible=True),
    _v("production_volume_bbl", "Production volume", "bbl", "PRODUCTION",
       VariableKind.CUMULATIVE, ml_eligible=True),
    _v("steam_volume_t", "Steam volume", "t", "STEAM_CSS", VariableKind.CUMULATIVE),
    _v("steam_injection_pressure_bar", "Steam injection pressure", "bar", "STEAM_CSS"),
    _v("soak_time_h", "Soak time", "h", "STEAM_CSS"),
    _v("css_phase", "CSS phase", "-", "STEAM_CSS", VariableKind.CATEGORICAL,
       chartable=False),
    _v("css_event", "CSS event", "event", "STEAM_CSS", VariableKind.EVENT,
       scopes=["WELL"], chartable=False),
    _v("production_cutoff", "Production cutoff", "-", "STEAM_CSS",
       VariableKind.CATEGORICAL, chartable=False),
    _v("spm", "Strokes per minute", "spm", "SRP", ml_eligible=True),
    _v("stroke_in", "Stroke length", "in", "SRP"),
    _v("vfd_percent", "VFD", "%", "SRP"),
    _v("pump_efficiency_percent", "Pump efficiency", "%", "SRP"),
    _v("pump_fillage_percent", "Pump fillage", "%", "SRP"),
    _v("rod_load", "Rod load", "-", "SRP", chartable=False),
    _v("pump_intake_pressure_bar", "Pump intake pressure", "bar", "SRP"),
    _v("wellhead_pressure_bar", "Wellhead pressure", "bar", "SURFACE"),
    _v("wellhead_temperature_c", "Wellhead temperature", "C", "SURFACE"),
    _v("energy_kwh", "Energy", "kWh", "ENERGY", VariableKind.CUMULATIVE),
    _v("steam_energy", "Steam energy", "kWh", "ENERGY", VariableKind.CUMULATIVE,
       chartable=False),
    _v("pumping_energy", "Pumping energy", "kWh", "ENERGY", VariableKind.CUMULATIVE,
       chartable=False),
    _v("sor", "Steam-oil ratio", "t/bbl", "PERFORMANCE"),
    _v("uptime_percent", "Uptime", "%", "PERFORMANCE"),
    _v("well_status", "Well status", "status", "PERFORMANCE",
       VariableKind.CATEGORICAL, chartable=False),
    _v("api_gravity", "API gravity", "API", "RESERVOIR"),
    _v("field_rate_bopd", "Field production rate", "bopd", "PRODUCTION",
       VariableKind.RATE, scopes=["FIELD"]),
    _v("annual_production_mt", "Annual production", "MT", "PRODUCTION",
       VariableKind.CUMULATIVE, scopes=["FIELD"]),
]:
    VARIABLE_REGISTRY[_spec.name] = _spec


class HistoricalObservation(BaseModel):
    """One historical fact with preserved temporal precision.

    value is None for range/event observations (see reported_min/max,
    value_kind). original_period keeps the source representation verbatim;
    timestamp_start/end are normalized UTC bounds for querying/sorting only.
    """

    record_id: str = Field(..., min_length=1)
    timestamp_start: str = Field(..., min_length=1)  # ISO date/datetime UTC
    timestamp_end: Optional[str] = None
    timestamp_precision: TemporalPrecision = TemporalPrecision.DAY
    original_period: str = ""
    approximate: bool = False
    well_id: Optional[str] = None  # null when field-level
    scope: ObservationScope = ObservationScope.WELL
    variable: str = Field(..., min_length=1)
    value: Optional[float] = None
    value_str: Optional[str] = None  # categorical/event labels
    reported_min: Optional[float] = None
    reported_max: Optional[float] = None
    unit: str = ""
    value_kind: ValueKind = ValueKind.MEASURED
    derivation: Optional[str] = None
    derived_from: Optional[str] = None
    source_id: str = "unspecified"
    provenance: ProvenanceClass = ProvenanceClass.UNKNOWN
    data_status: str = "PUBLIC_FIELD_RECORD"
    source_publication_date: Optional[str] = None
    time_series_safe: bool = False
    ml_safe: bool = False
    data_quality: str = "VALID"
    notes: str = ""
    extra: Dict[str, Any] = Field(default_factory=dict)


_FY_RE = re.compile(r"^FY(\d{4})-(\d{2})$")
_YM_RE = re.compile(r"^(\d{4})-(\d{2})$")
_Y_RE = re.compile(r"^(\d{4})$")
_D_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def _iso(d: date) -> str:
    return d.isoformat()


def normalize_period(period: str) -> Tuple[str, Optional[str], TemporalPrecision, bool]:
    """Normalize a source period to (start, end, precision, approximate).

    Never invents exactness: month stays MONTH, FY stays FINANCIAL_YEAR,
    ranges stay RANGE, undated stays APPROXIMATE. End is inclusive bound.
    """
    text = (period or "").strip()
    if not text or text.lower().startswith("undated"):
        return "1970-01-01", None, TemporalPrecision.APPROXIMATE, True
    if "/" in text:  # explicit range e.g. 2022-04/2022-08
        parts = [p.strip() for p in text.split("/", 1)]
        starts = [normalize_period(p) for p in parts]
        return starts[0][0], starts[1][1] or starts[1][0], TemporalPrecision.RANGE, True
    m = _FY_RE.match(text)  # Indian financial year Apr-Mar
    if m:
        y1 = int(m.group(1))
        return _iso(date(y1, 4, 1)), _iso(date(y1 + 1, 3, 31)), \
            TemporalPrecision.FINANCIAL_YEAR, False
    m = _YM_RE.match(text)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        last = calendar.monthrange(y, mo)[1]
        return _iso(date(y, mo, 1)), _iso(date(y, mo, last)), \
            TemporalPrecision.MONTH, False
    m = _Y_RE.match(text)
    if m:
        y = int(m.group(1))
        return _iso(date(y, 1, 1)), _iso(date(y, 12, 31)), \
            TemporalPrecision.YEAR, False
    m = _D_RE.match(text)
    if m:
        return text, text, TemporalPrecision.DAY, False
    try:  # full datetime
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.isoformat(), dt.isoformat(), TemporalPrecision.DATETIME, False
    except ValueError:
        return "1970-01-01", None, TemporalPrecision.APPROXIMATE, True


def validate_observation(obs: HistoricalObservation) -> Tuple[bool, str]:
    """Contract validation for one observation."""
    if obs.variable not in VARIABLE_REGISTRY:
        return False, f"unknown variable: {obs.variable}"
    spec = VARIABLE_REGISTRY[obs.variable]
    if obs.scope.value not in spec.scopes:
        return False, f"variable {obs.variable} not allowed at scope {obs.scope}"
    if obs.scope == ObservationScope.WELL and not obs.well_id:
        return False, "WELL scope requires well_id"
    if obs.scope == ObservationScope.FIELD and obs.well_id:
        return False, "FIELD scope must not carry well_id"
    if obs.value_kind == ValueKind.DERIVED_MIDPOINT:
        if obs.provenance != ProvenanceClass.DERIVED:
            return False, "derived midpoint must carry DERIVED provenance"
        if obs.reported_min is None or obs.reported_max is None or not obs.derivation:
            return False, "derived midpoint must preserve range + derivation"
    if obs.value_kind == ValueKind.REPORTED_RANGE:
        if obs.reported_min is None or obs.reported_max is None:
            return False, "reported range must carry min/max"
    if obs.provenance == ProvenanceClass.SYNTHETIC_BAGHEWALA \
            and obs.data_status != "SYNTHETIC_BAGHEWALA":
        return False, "synthetic provenance requires SYNTHETIC data_status"
    return True, ""


class HistoricalRepository(ABC):
    @abstractmethod
    def insert(self, obs: HistoricalObservation) -> bool: ...
    @abstractmethod
    def bulk_insert(self, items: List[HistoricalObservation]) -> Dict[str, int]: ...
    @abstractmethod
    def get(self, record_id: str) -> Optional[HistoricalObservation]: ...
    @abstractmethod
    def query(self, well_id: Optional[str] = None,
              scope: Optional[str] = None,
              variable: Optional[str] = None,
              start: Optional[str] = None, end: Optional[str] = None,
              provenance: Optional[List[str]] = None,
              precision: Optional[List[str]] = None,
              include_derived: bool = False,
              include_synthetic: bool = False,
              include_live: bool = True,
              limit: int = 100) -> List[HistoricalObservation]: ...
    @abstractmethod
    def counts(self) -> Dict[str, int]: ...


def _matches(obs: HistoricalObservation, well_id: Optional[str],
             scope: Optional[str], variable: Optional[str],
             start: Optional[str], end: Optional[str],
             provenance: Optional[List[str]], precision: Optional[List[str]],
             include_derived: bool, include_synthetic: bool,
             include_live: bool) -> bool:
    if well_id is not None and obs.well_id != well_id:
        return False
    if scope is not None and obs.scope.value != scope:
        return False
    if variable is not None and obs.variable != variable:
        return False
    if start is not None and (obs.timestamp_end or obs.timestamp_start) < start:
        return False
    if end is not None and obs.timestamp_start > end:
        return False
    if provenance is not None and obs.provenance.value not in provenance:
        return False
    if precision is not None and obs.timestamp_precision.value not in precision:
        return False
    if not include_derived and obs.provenance == ProvenanceClass.DERIVED:
        return False
    if not include_synthetic and (
            obs.provenance == ProvenanceClass.SYNTHETIC_BAGHEWALA
            or obs.data_status == "SYNTHETIC_BAGHEWALA"):
        return False
    if not include_live and obs.data_status == "LIVE_TELEMETRY":
        return False
    return True


class InMemoryHistoryRepository(HistoricalRepository):
    """Deterministic in-memory store: duplicate record_id never overwrites."""

    def __init__(self) -> None:
        self._obs: Dict[str, HistoricalObservation] = {}
        self.duplicates: int = 0

    def insert(self, obs: HistoricalObservation) -> bool:
        ok, _ = validate_observation(obs)
        if not ok:
            return False
        if obs.record_id in self._obs:
            self.duplicates += 1
            return False
        self._obs[obs.record_id] = obs
        return True

    def bulk_insert(self, items: List[HistoricalObservation]) -> Dict[str, int]:
        accepted = rejected = 0
        for obs in items:
            if self.insert(obs):
                accepted += 1
            else:
                rejected += 1
        return {"accepted": accepted, "rejected": rejected,
                "duplicates": self.duplicates}

    def get(self, record_id: str) -> Optional[HistoricalObservation]:
        return self._obs.get(record_id)

    def query(self, well_id: Optional[str] = None,
              scope: Optional[str] = None,
              variable: Optional[str] = None,
              start: Optional[str] = None, end: Optional[str] = None,
              provenance: Optional[List[str]] = None,
              precision: Optional[List[str]] = None,
              include_derived: bool = False,
              include_synthetic: bool = False,
              include_live: bool = True,
              limit: int = 100) -> List[HistoricalObservation]:
        limit = max(1, min(int(limit), 1000))
        out = [o for o in self._obs.values()
               if _matches(o, well_id, scope, variable, start, end,
                           provenance, precision, include_derived,
                           include_synthetic, include_live)]
        out.sort(key=lambda o: (o.timestamp_start, o.record_id))
        return out[:limit]

    def counts(self) -> Dict[str, int]:
        return {"observations": len(self._obs), "duplicates": self.duplicates}


class JsonlHistoryRepository(InMemoryHistoryRepository):
    """Append-safe JSONL file backing; reloads on construction."""

    def __init__(self, base_dir: str = "project/data/processed_history") -> None:
        super().__init__()
        self.base_dir = safe_base_dir(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)
        self._path = os.path.join(self.base_dir, "history.jsonl")
        self._reload()

    def _reload(self) -> None:
        if not os.path.exists(self._path):
            return
        with open(self._path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        self.insert(HistoricalObservation(**json.loads(line)))
                    except ValueError:
                        continue

    def insert(self, obs: HistoricalObservation) -> bool:
        if obs.record_id in self._obs:
            self.duplicates += 1
            return False
        ok = super().insert(obs)
        if ok:
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(obs.model_dump_json() + "\n")
        return ok


# ---------------- Phase 4: public-history builder ----------------

def _obs(record_id: str, period: str, scope: ObservationScope,
         variable: str, source_id: str, notes: str = "",
         well_id: Optional[str] = None, **kw: Any) -> HistoricalObservation:
    start, end, precision, approx = normalize_period(period)
    return HistoricalObservation(
        record_id=record_id, timestamp_start=start, timestamp_end=end,
        timestamp_precision=precision, original_period=period,
        approximate=approx, well_id=well_id, scope=scope, variable=variable,
        source_id=source_id, notes=notes, **kw,
    )


def build_public_history(boot: Dict[str, Any]) -> List[HistoricalObservation]:
    """Convert verified Priority-1 public records to historical observations.

    Only semantically valid conversions; sparse stays sparse; BGW-08 range
    yields a measured range observation + a DERIVED midpoint observation;
    BGW-17 keeps publication/event separation; field aggregates stay FIELD.
    """
    out: List[HistoricalObservation] = []

    for rec in boot.get("production_well", []):
        wid = rec.get("well_id", "")
        period = rec.get("event_period") or rec.get("period") or ""
        pub = rec.get("source_publication_date")
        if rec.get("value_kind") == "midpoint_of_reported_range":
            rid = rec.get("record_id", f"{wid}-PROD-RANGE")
            out.append(_obs(
                f"{rid}-RANGE", period, ObservationScope.WELL, "oil_rate_bopd",
                rec.get("source_id", ""), well_id=wid,
                value=None, value_kind=ValueKind.REPORTED_RANGE,
                reported_min=rec.get("reported_min_bopd"),
                reported_max=rec.get("reported_max_bopd"),
                unit=rec.get("unit", "bopd"),
                provenance=ProvenanceClass.BAGHEWALA_FIELD,
                data_status="PUBLIC_FIELD_RECORD",
                source_publication_date=pub, time_series_safe=False,
                ml_safe=False,
                notes="Source-reported range; no single measured value."))
            out.append(_obs(
                f"{rid}-MID", period, ObservationScope.WELL, "oil_rate_bopd",
                rec.get("source_id", ""), well_id=wid,
                value=rec.get("derived_midpoint_bopd"),
                value_kind=ValueKind.DERIVED_MIDPOINT,
                reported_min=rec.get("reported_min_bopd"),
                reported_max=rec.get("reported_max_bopd"),
                unit=rec.get("unit", "bopd"),
                derivation=rec.get("derivation"),
                derived_from=f"{rid}-RANGE",
                provenance=ProvenanceClass.DERIVED,
                data_status="DERIVED",
                source_publication_date=pub, time_series_safe=False,
                ml_safe=False,
                notes="Derived midpoint; never a raw measurement."))
        else:
            out.append(_obs(
                rec.get("record_id", f"{wid}-PROD"), period,
                ObservationScope.WELL, "oil_rate_bopd",
                rec.get("source_id", ""), well_id=wid,
                value=rec.get("value"), value_kind=ValueKind.REPORTED,
                unit=rec.get("unit", "bopd"),
                provenance=ProvenanceClass.BAGHEWALA_FIELD,
                data_status="PUBLIC_FIELD_RECORD",
                source_publication_date=pub, time_series_safe=False,
                ml_safe=False))

    for rec in boot.get("production_field", []):
        period = rec.get("period", "")
        kind = ValueKind.LOWER_BOUND if rec.get("value_kind") == "lower_bound" \
            else ValueKind.REPORTED
        var = "field_rate_bopd" if "field_rate" in rec.get("variable", "") \
            else "annual_production_mt"
        out.append(_obs(
            f"FIELD-{var}-{period}", period, ObservationScope.FIELD, var,
            rec.get("source_id", ""), value=rec.get("value"), value_kind=kind,
            unit=rec.get("unit", ""), provenance=ProvenanceClass.BAGHEWALA_FIELD,
            data_status="PUBLIC_FIELD_RECORD", time_series_safe=False,
            ml_safe=False,
            notes=rec.get("warning", "Field-level aggregate; never attach to a well.")))

    for rec in boot.get("css", []):
        wid = rec.get("well_id", "")
        period = rec.get("event_period", "")
        pub = rec.get("source_publication_date")
        out.append(_obs(
            rec.get("record_id", f"{wid}-CSS"), period,
            ObservationScope.WELL, "css_event",
            rec.get("source_id", ""), well_id=wid,
            value_str="CSS_CYCLE", value_kind=ValueKind.EVENT,
            unit="event", provenance=ProvenanceClass.BAGHEWALA_FIELD,
            data_status="PUBLIC_FIELD_RECORD",
            source_publication_date=pub, time_series_safe=False,
            ml_safe=False,
            notes=f"CSS cycle event period: {period}; exact timestamps not established."))

    return out


# ---------------- Phase 6: coverage and quality analysis ----------------

def compute_coverage(observations: List[HistoricalObservation]) -> Dict[str, Any]:
    """Compute coverage metadata for a set of observations."""
    if not observations:
        return {
            "observation_count": 0,
            "temporal_coverage": "NONE",
            "has_gaps": False,
            "duplicate_count": 0,
            "provenance_classes": [],
            "measured_count": 0,
            "derived_count": 0,
            "synthetic_count": 0,
            "insufficient_count": 0,
            "time_series_safe_count": 0,
            "ml_safe_count": 0,
        }

    prov_classes = {}
    precision_counts = {}
    measured = derived = synthetic = ts_safe = ml_safe = 0

    for obs in observations:
        p = obs.provenance.value
        prov_classes[p] = prov_classes.get(p, 0) + 1
        prec = obs.timestamp_precision.value
        precision_counts[prec] = precision_counts.get(prec, 0) + 1
        if obs.provenance == ProvenanceClass.BAGHEWALA_FIELD and \
                obs.value_kind in (ValueKind.MEASURED, ValueKind.REPORTED,
                                   ValueKind.REPORTED_RANGE):
            measured += 1
        if obs.provenance == ProvenanceClass.DERIVED:
            derived += 1
        if obs.provenance == ProvenanceClass.SYNTHETIC_BAGHEWALA or \
                obs.data_status == "SYNTHETIC_BAGHEWALA":
            synthetic += 1
        if obs.time_series_safe:
            ts_safe += 1
        if obs.ml_safe:
            ml_safe += 1

    # Determine temporal coverage
    sorted_obs = sorted(observations, key=lambda o: o.timestamp_start)
    start = sorted_obs[0].timestamp_start
    end = (sorted_obs[-1].timestamp_end or sorted_obs[-1].timestamp_start)
    coverage_str = f"{start} to {end}"

    # Simple gap detection: check for large jumps in time
    has_gaps = False
    if len(sorted_obs) > 1:
        for i in range(1, len(sorted_obs)):
            curr_start = sorted_obs[i].timestamp_start
            prev_end = sorted_obs[i-1].timestamp_end or sorted_obs[i-1].timestamp_start
            # If gap > 90 days, flag as gap (heuristic)
            try:
                from datetime import datetime
                d1 = datetime.fromisoformat(prev_end)
                d2 = datetime.fromisoformat(curr_start)
                if (d2 - d1).days > 90:
                    has_gaps = True
                    break
            except (ValueError, TypeError):
                pass

    return {
        "observation_count": len(observations),
        "temporal_coverage": coverage_str,
        "has_gaps": has_gaps,
        "duplicate_count": 0,  # Repository level tracks this
        "provenance_classes": sorted(prov_classes.keys()),
        "measured_count": measured,
        "derived_count": derived,
        "synthetic_count": synthetic,
        "insufficient_count": len(observations) - ts_safe,
        "time_series_safe_count": ts_safe,
        "ml_safe_count": ml_safe,
        "precision_breakdown": precision_counts,
    }


def well_coverage_summary(repo: HistoricalRepository, well_id: str) -> Dict[str, Any]:
    """Coverage summary for a specific well."""
    obs = repo.query(well_id=well_id, include_derived=True,
                     include_synthetic=True, include_live=True, limit=1000)
    coverage = compute_coverage(obs)

    # Count by variable
    var_counts = {}
    for o in obs:
        var_counts[o.variable] = var_counts.get(o.variable, 0) + 1

    return {
        "well_id": well_id,
        "coverage": coverage,
        "variables": var_counts,
        "time_series_ready": coverage["time_series_safe_count"] >= MIN_OBSERVATIONS_FOR_TREND,
        "ml_ready": coverage["ml_safe_count"] >= MIN_OBSERVATIONS_FOR_TREND,
    }


# ---------------- Phase 10: safe aggregation ----------------

def safe_aggregate(observations: List[HistoricalObservation],
                   operation: str) -> Dict[str, Any]:
    """Perform safe aggregation with warnings where appropriate.

    Operations: count, min, max, mean, median, sum, latest, earliest.
    Refuses to aggregate inappropriate data types.
    """
    if not observations:
        return {"operation": operation, "result": None, "count": 0,
                "warnings": ["No observations to aggregate"]}

    var = observations[0].variable
    spec = VARIABLE_REGISTRY.get(var)
    if not spec:
        return {"operation": operation, "result": None, "count": len(observations),
                "warnings": [f"Unknown variable: {var}"]}

    warnings = []
    numeric_values = []

    for obs in observations:
        if obs.variable != var:
            warnings.append(f"Variable mismatch: {obs.variable} vs {var}")
            continue
        if obs.value is not None:
            numeric_values.append(obs.value)
        elif obs.value_str is not None:
            warnings.append(f"Categorical value cannot be aggregated numerically: {obs.value_str}")

    # Refuse inappropriate operations
    if operation in ("sum", "mean", "median"):
        if spec.kind in (VariableKind.EVENT, VariableKind.CATEGORICAL):
            return {"operation": operation, "result": None, "count": len(observations),
                    "warnings": [f"Cannot {operation} categorical/event variable {var}"]}
        if spec.kind == VariableKind.RATE and operation == "sum":
            warnings.append(f"Summing rate variable {var} is physically meaningless")

    if operation == "count":
        return {"operation": operation, "result": len(observations),
                "count": len(observations), "warnings": warnings}

    if not numeric_values:
        return {"operation": operation, "result": None, "count": len(observations),
                "warnings": warnings + ["No numeric values to aggregate"]}

    if operation == "min":
        return {"operation": operation, "result": min(numeric_values),
                "count": len(numeric_values), "warnings": warnings}
    if operation == "max":
        return {"operation": operation, "result": max(numeric_values),
                "count": len(numeric_values), "warnings": warnings}
    if operation == "sum":
        return {"operation": operation, "result": sum(numeric_values),
                "count": len(numeric_values), "warnings": warnings}
    if operation == "mean":
        return {"operation": operation, "result": sum(numeric_values) / len(numeric_values),
                "count": len(numeric_values), "warnings": warnings}
    if operation == "median":
        sorted_vals = sorted(numeric_values)
        n = len(sorted_vals)
        mid = n // 2
        median = (sorted_vals[mid] + sorted_vals[mid - 1]) / 2 if n % 2 == 0 else sorted_vals[mid]
        return {"operation": operation, "result": median,
                "count": len(numeric_values), "warnings": warnings}
    if operation == "latest":
        latest = max(observations, key=lambda o: o.timestamp_start)
        return {"operation": operation, "result": latest.value or latest.value_str,
                "timestamp": latest.timestamp_start, "count": len(observations),
                "warnings": warnings}
    if operation == "earliest":
        earliest = min(observations, key=lambda o: o.timestamp_start)
        return {"operation": operation, "result": earliest.value or earliest.value_str,
                "timestamp": earliest.timestamp_start, "count": len(observations),
                "warnings": warnings}

    return {"operation": operation, "result": None, "count": len(observations),
            "warnings": warnings + [f"Unknown operation: {operation}"]}


# ---------------- Phase 11: trend and gap analysis ----------------

def analyze_trend(observations: List[HistoricalObservation]) -> Dict[str, Any]:
    """Analyze a time series for trend eligibility and basic statistics.

    Returns INSUFFICIENT for sparse series; never fabricates trends.
    """
    if not observations:
        return {
            "status": "INSUFFICIENT",
            "reason": "No observations",
            "observation_count": 0,
        }

    # Check temporal precision
    eligible_precision = any(
        o.timestamp_precision.value in TREND_ELIGIBLE_PRECISION
        for o in observations
    )

    if not eligible_precision:
        return {
            "status": "INSUFFICIENT",
            "reason": f"Temporal precision not eligible for trend analysis. "
                     f"Required: {TREND_ELIGIBLE_PRECISION}, found: "
                     f"{set(o.timestamp_precision.value for o in observations)}",
            "observation_count": len(observations),
        }

    if len(observations) < MIN_OBSERVATIONS_FOR_TREND:
        return {
            "status": "INSUFFICIENT",
            "reason": f"Insufficient observations for trend (need {MIN_OBSERVATIONS_FOR_TREND}, have {len(observations)})",
            "observation_count": len(observations),
        }

    # Extract numeric values
    numeric_vals = [(o.timestamp_start, o.value) for o in observations if o.value is not None]
    if len(numeric_vals) < MIN_OBSERVATIONS_FOR_TREND:
        return {
            "status": "INSUFFICIENT",
            "reason": f"Insufficient numeric values for trend (need {MIN_OBSERVATIONS_FOR_TREND}, have {len(numeric_vals)})",
            "observation_count": len(observations),
            "numeric_count": len(numeric_vals),
        }

    # Basic trend direction (simple first-last comparison)
    sorted_vals = sorted(numeric_vals, key=lambda x: x[0])
    first_val = sorted_vals[0][1]
    last_val = sorted_vals[-1][1]
    change = last_val - first_val
    change_pct = (change / first_val * 100) if first_val != 0 else None

    direction = "STABLE"
    if change > 0:
        direction = "INCREASING"
    elif change < 0:
        direction = "DECREASING"

    return {
        "status": "TREND_AVAILABLE",
        "observation_count": len(observations),
        "numeric_count": len(numeric_vals),
        "temporal_precision": set(o.timestamp_precision.value for o in observations),
        "first_value": first_val,
        "last_value": last_val,
        "change": change,
        "change_percent": change_pct,
        "direction": direction,
        "min_value": min(v for _, v in numeric_vals),
        "max_value": max(v for _, v in numeric_vals),
        "mean_value": sum(v for _, v in numeric_vals) / len(numeric_vals),
    }
