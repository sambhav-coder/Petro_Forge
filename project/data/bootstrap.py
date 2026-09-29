"""Startup bootstrap for verified public Baghewala data (Recovery phase).

Loads project/data/public/*.json, validates each record against light
schemas, rejects malformed entries with counts. Prints a short summary.
Trusted project assets, but STILL schema-validated (Objective 35).
"""

import json
import os
from typing import Any, Dict, List, Tuple

PUBLIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")

REQUIRED_WELL_FIELDS = {"well_id", "field", "provenance"}
VALID_PROVENANCE = {"BAGHEWALA_FIELD", "PUBLIC_REFERENCE", "SYNTHETIC_BAGHEWALA",
                    "DERIVED", "UNKNOWN"}


def _load(name: str) -> Any:
    path = os.path.join(PUBLIC_DIR, name)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _valid_well(rec: Dict[str, Any]) -> Tuple[bool, str]:
    if not isinstance(rec, dict):
        return False, "not an object"
    missing = REQUIRED_WELL_FIELDS - set(rec.keys())
    if missing:
        return False, f"missing {sorted(missing)}"
    if not isinstance(rec["well_id"], str) or not rec["well_id"].strip():
        return False, "bad well_id"
    if rec.get("provenance") not in VALID_PROVENANCE:
        return False, "bad provenance"
    return True, ""


def _valid_css(rec: Dict[str, Any]) -> Tuple[bool, str]:
    if not isinstance(rec, dict):
        return False, "not an object"
    if not rec.get("cycle_id") or not rec.get("well_id"):
        return False, "missing cycle_id/well_id"
    if rec.get("provenance") not in VALID_PROVENANCE:
        return False, "bad provenance"
    return True, ""


def _valid_production(rec: Dict[str, Any], well_specific: bool) -> Tuple[bool, str]:
    if not isinstance(rec, dict):
        return False, "not an object"
    if well_specific and not rec.get("well_id"):
        return False, "missing well_id"
    if not isinstance(rec.get("value"), (int, float)):
        return False, "bad value"
    if not rec.get("unit") or not rec.get("source_id"):
        return False, "missing unit/source_id"
    return True, ""


def bootstrap_public_data() -> Dict[str, Any]:
    """Load + validate public files. Returns registries + report counts."""
    wells_doc = _load("baghewala_wells.json")
    css_doc = _load("baghewala_css.json")
    prod_doc = _load("baghewala_production.json")
    field_doc = _load("baghewala_field.json")

    wells: Dict[str, Dict[str, Any]] = {}
    rejected = 0
    for rec in wells_doc.get("wells", []):
        ok, _ = _valid_well(rec)
        if ok:
            wells[rec["well_id"]] = rec
        else:
            rejected += 1

    css: List[Dict[str, Any]] = []
    for rec in css_doc.get("records", []):
        ok, _ = _valid_css(rec)
        if ok:
            css.append(rec)
        else:
            rejected += 1

    prod_well: List[Dict[str, Any]] = []
    for rec in prod_doc.get("well_specific", []):
        ok, _ = _valid_production(rec, True)
        if ok:
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

    report = {
        "public_wells": len(wells),
        "public_production_records": len(prod_well) + len(prod_field),
        "public_css_records": len(css),
        "synthetic_records": 0,
        "rejected_records": rejected,
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
        "report": report,
    }
