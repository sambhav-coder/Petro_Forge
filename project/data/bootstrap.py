"""Startup bootstrap for verified public Baghewala data (Recovery phase).

Loads project/data/public/*.json, validates each record against hardened
Priority-1 data-contract rules, rejects malformed entries with counts.
Trusted project assets, but STILL schema-validated.

Hardened contract rules (Priority 1 final):
- well_id format ``BGW-<digits>``; CSS/production well refs must resolve
- provenance must be a known class; public records must never be synthetic
- every observation source_id component must exist in data_sources.json
- dates carry explicit precision; publication dates never accepted as
  operational event dates (BGW-17 injection_end must stay null)
- derived values (BGW-08 85 BOPD) must carry range + derivation metadata
- field-level scope must never leak onto well records
- duplicate well_id / cycle_id / record_id rejected deterministically
"""

import json
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

PUBLIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")
CATALOG_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data_catalog")
)

REQUIRED_WELL_FIELDS = {"well_id", "field", "provenance"}
VALID_PROVENANCE = {"BAGHEWALA_FIELD", "PUBLIC_REFERENCE", "SYNTHETIC_BAGHEWALA",
                    "DERIVED", "UNKNOWN"}

WELL_ID_RE = re.compile(r"^BGW-\d{2}$")
DATE_RE = re.compile(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$")
VALID_DATE_PRECISION = {"year", "month", "day"}
VALID_STATUS_AS_OF_KIND = {
    "event_date", "event_period_end_approximate", "event_period_month",
    "event_period_approximate", "event_month",
    "source_publication_date", "publication_date",
}

_source_cache: Optional[Set[str]] = None


def _load(name: str) -> Any:
    path = os.path.join(PUBLIC_DIR, name)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def known_source_ids() -> Set[str]:
    """All source_id values registered in data_sources.json."""
    global _source_cache
    if _source_cache is not None:
        return _source_cache
    path = os.path.join(CATALOG_DIR, "data_sources.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
        _source_cache = {s.get("source_id", "") for s in doc.get("sources", [])}
    except (OSError, ValueError):
        _source_cache = set()
    return _source_cache


def _check_sources(source_id: Any) -> Tuple[bool, str]:
    if not isinstance(source_id, str) or not source_id.strip():
        return False, "missing source_id"
    known = known_source_ids()
    if not known:
        return True, ""  # catalog unavailable: do not hard-fail boot
    for part in source_id.split("+"):
        part = part.strip()
        if not part:
            return False, "empty source_id component"
        if part not in known:
            return False, f"unknown source_id component: {part}"
    return True, ""


def _check_date(value: Any, field: str, allow_none: bool = True) -> Tuple[bool, str]:
    if value is None:
        return (True, "") if allow_none else (False, f"missing {field}")
    if not isinstance(value, str):
        return False, f"bad {field}: not a string"
    if not DATE_RE.match(value.strip()):
        return False, f"bad {field} format: {value!r} (expected YYYY, YYYY-MM, or YYYY-MM-DD)"
    return True, ""


def _valid_well(rec: Dict[str, Any]) -> Tuple[bool, str]:
    if not isinstance(rec, dict):
        return False, "not an object"
    missing = REQUIRED_WELL_FIELDS - set(rec.keys())
    if missing:
        return False, f"missing {sorted(missing)}"
    wid = rec.get("well_id")
    if not isinstance(wid, str) or not WELL_ID_RE.match(wid.strip()):
        return False, "bad well_id (expected BGW-NN)"
    if rec.get("provenance") not in VALID_PROVENANCE:
        return False, "bad provenance"
    if rec.get("provenance") == "SYNTHETIC_BAGHEWALA":
        return False, "public registry must never carry synthetic provenance"
    if rec.get("is_synthetic") is True:
        return False, "public registry must never be flagged synthetic"
    if rec.get("is_telemetry") is True:
        return False, "public registry must never claim telemetry"
    if rec.get("scope") not in (None, "WELL_LEVEL"):
        return False, "well record scope must be WELL_LEVEL"
    if "source_id" in rec:
        ok, msg = _check_sources(rec.get("source_id"))
        if not ok:
            return False, msg
    for f in ("status_as_of", "source_publication_date"):
        ok, msg = _check_date(rec.get(f), f)
        if not ok:
            return False, msg
    prec = rec.get("date_precision")
    if prec is not None and prec not in VALID_DATE_PRECISION:
        return False, f"bad date_precision: {prec!r}"
    kind = rec.get("status_as_of_kind")
    if kind is not None and kind not in VALID_STATUS_AS_OF_KIND:
        return False, f"bad status_as_of_kind: {kind!r}"
    return True, ""


def _valid_css(rec: Dict[str, Any], known_wells: Optional[Set[str]] = None) -> Tuple[bool, str]:
    if not isinstance(rec, dict):
        return False, "not an object"
    if not rec.get("cycle_id") or not rec.get("well_id"):
        return False, "missing cycle_id/well_id"
    if not isinstance(rec["well_id"], str) or not WELL_ID_RE.match(rec["well_id"].strip()):
        return False, "bad well_id (expected BGW-NN)"
    if known_wells is not None and rec["well_id"] not in known_wells:
        return False, f"unknown well reference: {rec['well_id']}"
    if rec.get("provenance") not in VALID_PROVENANCE:
        return False, "bad provenance"
    if rec.get("is_synthetic") is True or rec.get("is_telemetry") is True:
        return False, "public CSS record must not claim synthetic/telemetry"
    if rec.get("scope") not in (None, "WELL_LEVEL"):
        return False, "CSS record scope must be WELL_LEVEL"
    if "source_id" in rec:
        ok, msg = _check_sources(rec.get("source_id"))
        if not ok:
            return False, msg
    for f in ("injection_start", "injection_end", "soak_start", "soak_end",
              "production_start", "production_end", "source_publication_date"):
        ok, msg = _check_date(rec.get(f), f)
        if not ok:
            return False, msg
    # Temporal-semantics guard: a publication date must never double as an
    # operational date. BGW-17's vendor publication date lives only in
    # source_publication_date; injection_end must stay null.
    if rec.get("well_id") == "BGW-17-CSS-2022" or rec.get("cycle_id") == "BGW-17-CSS-2022":
        if rec.get("injection_end") == "2022-08-02":
            return False, "injection_end must not reuse vendor publication date 2022-08-02"
    if rec.get("cycle_id") == "BGW-17-CSS-2022" and rec.get("injection_end") is not None:
        return False, "BGW-17 exact operational end not established; injection_end must be null"
    prec = rec.get("date_precision")
    if prec is not None and prec not in VALID_DATE_PRECISION:
        return False, f"bad date_precision: {prec!r}"
    return True, ""


def _valid_production(
    rec: Dict[str, Any], well_specific: bool, known_wells: Optional[Set[str]] = None
) -> Tuple[bool, str]:
    if not isinstance(rec, dict):
        return False, "not an object"
    if well_specific:
        if not rec.get("well_id"):
            return False, "missing well_id"
        if not isinstance(rec["well_id"], str) or not WELL_ID_RE.match(rec["well_id"].strip()):
            return False, "bad well_id (expected BGW-NN)"
        if known_wells is not None and rec["well_id"] not in known_wells:
            return False, f"unknown well reference: {rec['well_id']}"
        if rec.get("scope") not in (None, "WELL_LEVEL"):
            return False, "well production scope must be WELL_LEVEL"
    else:
        if rec.get("well_id"):
            return False, "field-level record must not carry well_id"
        if rec.get("scope") not in (None, "FIELD_LEVEL"):
            return False, "field production scope must be FIELD_LEVEL"
    if not isinstance(rec.get("value"), (int, float)):
        return False, "bad value"
    if isinstance(rec.get("value"), bool):
        return False, "bad value"
    if not rec.get("unit") or not rec.get("source_id"):
        return False, "missing unit/source_id"
    ok, msg = _check_sources(rec.get("source_id"))
    if not ok:
        return False, msg
    if rec.get("is_synthetic") is True or rec.get("is_telemetry") is True:
        return False, "public production record must not claim synthetic/telemetry"
    # Derived-value contract: midpoint_of_reported_range must expose the raw
    # range and its derivation so 85 BOPD can never read as a raw measurement.
    if rec.get("value_kind") == "midpoint_of_reported_range":
        for f in ("reported_min_bopd", "reported_max_bopd", "derived_midpoint_bopd",
                  "derivation", "derived_from"):
            if rec.get(f) in (None, ""):
                return False, f"derived midpoint missing {f}"
        try:
            lo = float(rec["reported_min_bopd"])
            hi = float(rec["reported_max_bopd"])
            mid = float(rec["derived_midpoint_bopd"])
        except (TypeError, ValueError):
            return False, "derived range fields must be numeric"
        if not abs(mid - (lo + hi) / 2.0) < 1e-9:
            return False, "derived midpoint inconsistent with reported range"
        if float(rec["value"]) != mid:
            return False, "value must equal derived midpoint"
    return True, ""


def _valid_coverage(doc: Dict[str, Any], wells: Dict[str, Any]) -> Tuple[bool, str]:
    if not isinstance(doc, dict) or not isinstance(doc.get("wells"), list):
        return False, "coverage file malformed"
    cov_ids = [w.get("well_id") for w in doc["wells"]]
    if set(cov_ids) != set(wells):
        return False, "coverage well set must match public registry"
    for w in doc["wells"]:
        for f in ("well_registry", "status_records", "css_records",
                  "production_records", "telemetry_data"):
            if f not in w:
                return False, f"coverage {w.get('well_id')} missing {f}"
        if w.get("telemetry_data") is not False:
            return False, f"coverage {w.get('well_id')}: telemetry_data must be false"
        # Cross-check flags against loaded registries is done by the caller.
    return True, ""


def validate_public_well_record(rec: Dict[str, Any]) -> Tuple[bool, str]:
    """Explicit PublicWellRecord validator (Fix #5)."""
    return _valid_well(rec)


def validate_public_css_event(
    rec: Dict[str, Any], known_wells: Optional[Set[str]] = None
) -> Tuple[bool, str]:
    """Explicit PublicCSSEvent validator (Fix #5)."""
    return _valid_css(rec, known_wells)


def validate_public_production_observation(
    rec: Dict[str, Any], known_wells: Optional[Set[str]] = None
) -> Tuple[bool, str]:
    """Explicit PublicProductionObservation validator (Fix #5)."""
    return _valid_production(rec, True, known_wells)


def validate_field_observation(rec: Dict[str, Any]) -> Tuple[bool, str]:
    """Explicit FieldObservation validator (Fix #5)."""
    return _valid_production(rec, False)


def validate_coverage_record(doc: Dict[str, Any], wells: Dict[str, Any]) -> Tuple[bool, str]:
    """Explicit CoverageRecord validator (Fix #5)."""
    return _valid_coverage(doc, wells)


def bootstrap_public_data() -> Dict[str, Any]:
    """Load + validate public files. Returns registries + report counts."""
    wells_doc = _load("baghewala_wells.json")
    css_doc = _load("baghewala_css.json")
    prod_doc = _load("baghewala_production.json")
    field_doc = _load("baghewala_field.json")
    try:
        coverage_doc = _load("baghewala_well_coverage.json")
    except (OSError, ValueError):
        coverage_doc = {}

    wells: Dict[str, Dict[str, Any]] = {}
    rejected = 0
    for rec in wells_doc.get("wells", []):
        ok, _ = _valid_well(rec)
        if ok:
            if rec["well_id"] in wells:
                rejected += 1  # duplicate well_id rejected deterministically
            else:
                wells[rec["well_id"]] = rec
        else:
            rejected += 1

    css: List[Dict[str, Any]] = []
    seen_cycles: Set[str] = set()
    for rec in css_doc.get("records", []):
        ok, _ = _valid_css(rec, set(wells))
        if ok:
            if rec["cycle_id"] in seen_cycles:
                rejected += 1
            else:
                seen_cycles.add(rec["cycle_id"])
                css.append(rec)
        else:
            rejected += 1

    prod_well: List[Dict[str, Any]] = []
    seen_records: Set[str] = set()
    for rec in prod_doc.get("well_specific", []):
        ok, _ = _valid_production(rec, True, set(wells))
        if ok:
            rid = rec.get("record_id", f"{rec.get('well_id')}:{rec.get('variable')}:{rec.get('value')}")
            if rid in seen_records:
                rejected += 1
            else:
                seen_records.add(rid)
                prod_well.append(rec)
        else:
            rejected += 1

    prod_field: List[Dict[str, Any]] = []
    for rec in prod_doc.get("field_level", []):
        ok, _ = _valid_production(rec, False)
        if ok:
            prod_field.append(rec)
        else:
            rejected += 1

    coverage_ok, _ = _valid_coverage(coverage_doc, wells) if coverage_doc else (False, "missing")
    # Cross-check coverage flags against actual registries.
    css_wells = {c["well_id"] for c in css}
    prod_wells = {p["well_id"] for p in prod_well}
    if coverage_doc and isinstance(coverage_doc.get("wells"), list):
        for w in coverage_doc["wells"]:
            wid = w.get("well_id")
            if wid not in wells:
                continue
            if bool(w.get("css_records")) != (wid in css_wells):
                rejected += 1
                break
            if bool(w.get("production_records")) != (wid in prod_wells):
                rejected += 1
                break

    report = {
        "public_wells": len(wells),
        "public_production_records": len(prod_well) + len(prod_field),
        "public_css_records": len(css),
        "synthetic_records": 0,
        "rejected_records": rejected,
        "coverage_valid": coverage_ok,
    }
    print("PetroForge data bootstrap: "
          f"Baghewala public wells loaded: {report['public_wells']}; "
          f"Public production records: {report['public_production_records']}; "
          f"Public CSS records: {report['public_css_records']}; "
          f"Synthetic records: 0; Rejected records: {rejected}.")
    return {
        "wells": wells,
        "css": css,
        "production_well": prod_well,
        "production_field": prod_field,
        "field": field_doc,
        "coverage": coverage_doc,
        "report": report,
    }
