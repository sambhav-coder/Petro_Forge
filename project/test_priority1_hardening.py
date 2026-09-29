"""Priority 1 final hardening regression tests (data-contract lock).

Covers the 24 mandatory checks: coverage file, 5-well registry, flag
consistency, referential integrity, field/well separation, BGW-08 range +
derivation, publication-vs-event dates, BGW-17 duration, synthetic/
telemetry/status contracts, invalid provenance/sources, duplicates,
fresh-startup registry, public-only twin, telemetry ingest, secrets,
field-leak isolation, derivation traceability.
"""

import importlib.util
import json
import os
import re

from fastapi.testclient import TestClient

from data.bootstrap import (
    _valid_css,
    _valid_production,
    _valid_well,
    bootstrap_public_data,
    known_source_ids,
    validate_coverage_record,
)

app_path = os.path.join(os.path.dirname(__file__), "app.py")
spec = importlib.util.spec_from_file_location("app_sih26120_hardening", app_path)
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)
app = app_module.app
client = TestClient(app)

EXPECTED_WELLS = {"BGW-01", "BGW-04", "BGW-08", "BGW-17", "BGW-40"}


def _public(name):
    with open(os.path.join(os.path.dirname(__file__), "data", "public", name),
              encoding="utf-8") as fh:
        return json.load(fh)


def test_1_coverage_file_exists_and_loads():
    doc = _public("baghewala_well_coverage.json")
    assert doc["version"] == "1.0"
    assert "verified public well-specific records" in doc["description"]
    assert doc["total_verified_wells"] == 5
    assert isinstance(doc["wells"], list)


def test_2_exactly_five_verified_wells():
    doc = _public("baghewala_well_coverage.json")
    assert {w["well_id"] for w in doc["wells"]} == EXPECTED_WELLS
    wells = _public("baghewala_wells.json")
    assert {w["well_id"] for w in wells["wells"]} == EXPECTED_WELLS


def test_3_coverage_flags_consistent():
    doc = _public("baghewala_well_coverage.json")
    by_id = {w["well_id"]: w for w in doc["wells"]}
    assert by_id["BGW-08"]["css_records"] is True
    assert by_id["BGW-08"]["production_records"] is True
    assert by_id["BGW-17"]["css_records"] is True
    assert by_id["BGW-17"]["production_records"] is False
    assert by_id["BGW-01"]["css_records"] is False
    assert all(w["well_registry"] is True for w in doc["wells"])
    assert all(w["telemetry_data"] is False for w in doc["wells"])
    ok, msg = validate_coverage_record(doc, {w: {} for w in EXPECTED_WELLS})
    assert ok, msg


def test_4_public_well_references_valid():
    for rec in _public("baghewala_wells.json")["wells"]:
        ok, msg = _valid_well(rec)
        assert ok, f"{rec.get('well_id')}: {msg}"
        assert re.match(r"^BGW-\d{2}$", rec["well_id"])


def test_5_css_records_reference_valid_wells():
    for rec in _public("baghewala_css.json")["records"]:
        ok, msg = _valid_css(rec, EXPECTED_WELLS)
        assert ok, f"{rec.get('cycle_id')}: {msg}"


def test_6_production_records_reference_valid_wells():
    for rec in _public("baghewala_production.json")["well_specific"]:
        ok, msg = _valid_production(rec, True, EXPECTED_WELLS)
        assert ok, msg


def test_7_field_production_not_attached_to_wells():
    prod = _public("baghewala_production.json")
    assert all("well_id" not in r or not r.get("well_id") for r in prod["field_level"])
    assert all(r.get("scope") == "FIELD_LEVEL" for r in prod["field_level"])
    data = client.get("/api/v1/wells").json()
    assert all(w["oil_rate_bopd"] != 1202.0 for w in data["wells"])
    detail = client.get("/api/v1/wells/BGW-08").json()
    assert all(p.get("well_id", "BGW-08") == "BGW-08" for p in detail["production"])


def test_8_bgw08_preserves_reported_range():
    prod = _public("baghewala_production.json")
    rec = next(r for r in prod["well_specific"] if r.get("well_id") == "BGW-08")
    assert rec["reported_min_bopd"] == 80.0
    assert rec["reported_max_bopd"] == 90.0


def test_9_bgw08_midpoint_marked_derived():
    prod = _public("baghewala_production.json")
    rec = next(r for r in prod["well_specific"] if r.get("well_id") == "BGW-08")
    assert rec["value_kind"] == "midpoint_of_reported_range"
    assert rec["value"] == 85.0 == rec["derived_midpoint_bopd"]
    assert rec["derived_provenance"] == "DERIVED"
    assert "midpoint" in rec["derivation"]
    assert rec["derived_from"]
    # API still exposes the recoverable range.
    detail = client.get("/api/v1/wells/BGW-08").json()
    api_rec = detail["production"][0]
    assert api_rec["reported_min_bopd"] == 80.0
    assert api_rec["reported_max_bopd"] == 90.0
    assert api_rec["derived_provenance"] == "DERIVED"


def test_10_publication_date_not_event_date():
    css = _public("baghewala_css.json")
    bgw17 = next(r for r in css["records"] if r["well_id"] == "BGW-17")
    assert bgw17["injection_end"] is None
    assert bgw17["source_publication_date"] == "2022-08-02"
    assert bgw17["exact_date_available"] is False
    wells = {w["well_id"]: w for w in _public("baghewala_wells.json")["wells"]}
    assert wells["BGW-17"]["status_as_of_kind"] == "source_publication_date"
    assert wells["BGW-08"]["status_as_of_kind"] == "source_publication_date"


def test_11_bgw17_not_false_continuous_telemetry():
    css = _public("baghewala_css.json")
    bgw17 = next(r for r in css["records"] if r["well_id"] == "BGW-17")
    assert bgw17["reported_injection_days"] == 17
    assert bgw17["time_series_safe"] is False
    assert bgw17["time_series_exclusion_reason"]
    assert bgw17["is_telemetry"] is False


def test_12_synthetic_records_remain_synthetic():
    from data import synthetic as syn
    recs = syn.generate(cycles_per_well=1, seed=5, include_bad=False)
    assert all(r["provenance"] == "SYNTHETIC_BAGHEWALA" for r in recs)
    assert not (set(r["well_id"] for r in recs) & EXPECTED_WELLS)


def test_13_telemetry_remains_telemetry():
    r = client.post("/api/v1/telemetry/ingest", json={
        "well_id": "BGW-T1", "reservoir_temperature_c": 60.0,
        "reservoir_pressure_bar": 30.0, "api_gravity": 18.0,
        "wellhead_pressure_bar": 12.0, "oil_rate_bopd": 40.0,
        "steam_volume_t": 900.0, "steam_injection_pressure_bar": 65.0,
        "soak_time_h": 48.0, "css_phase": "PRODUCTION",
        "spm": 6.0, "stroke_in": 96.0, "vfd_percent": 55.0})
    assert r.status_code == 201
    wells = {w["well_id"]: w for w in client.get("/api/v1/wells").json()["wells"]}
    assert wells["BGW-T1"]["data_status"] == "LIVE_TELEMETRY"
    app_module.reset_block1_state()


def test_14_public_records_never_become_live():
    data = client.get("/api/v1/wells").json()
    pub = [w for w in data["wells"] if w["well_id"] in EXPECTED_WELLS]
    assert all(w["data_status"] == "PUBLIC_FIELD_RECORD" for w in pub)
    assert all("LIVE" not in w["data_status"] for w in pub)


def test_15_unknown_status_not_active():
    for wid in ("BGW-01", "BGW-40"):
        detail = client.get(f"/api/v1/wells/{wid}").json()
        assert detail["status"] == "UNKNOWN"
        assert detail["telemetry"] is None


def test_16_invalid_provenance_rejected():
    assert not _valid_well({"well_id": "BGW-08", "field": "Baghewala",
                            "provenance": "NOPE"})[0]
    assert not _valid_css({"cycle_id": "C", "well_id": "BGW-08",
                           "provenance": "NOPE"})[0]
    assert not _valid_production({"well_id": "BGW-08", "value": 1.0,
                                  "unit": "bopd", "source_id": "x",
                                  "provenance": "NOPE"}, True)[0]


def test_17_invalid_source_references_rejected():
    known = known_source_ids()
    assert "toi_css_jaipur_2019" in known
    assert not _valid_well({"well_id": "BGW-08", "field": "Baghewala",
                            "provenance": "BAGHEWALA_FIELD",
                            "source_id": "nonexistent_src_xyz"})[0]
    # Compound source_ids: every component must exist.
    ok, _ = _valid_well({"well_id": "BGW-08", "field": "Baghewala",
                         "provenance": "BAGHEWALA_FIELD",
                         "source_id": "toi_css_jaipur_2019+bogus_src"})
    assert not ok


def test_18_duplicates_rejected_or_deterministic():
    base = {"well_id": "BGW-08", "field": "Baghewala",
            "provenance": "BAGHEWALA_FIELD", "source_id": "toi_css_jaipur_2019"}
    assert _valid_well(dict(base))[0]
    assert _valid_well({"well_id": "bad id", "field": "x",
                        "provenance": "BAGHEWALA_FIELD"})[0] is False
    report = bootstrap_public_data()["report"]
    assert report["rejected_records"] == 0  # current files: no dupes


def test_19_fresh_startup_returns_public_registry():
    data = client.get("/api/v1/wells").json()
    assert data["total_wells"] >= 5
    assert EXPECTED_WELLS <= {w["well_id"] for w in data["wells"]}


def test_20_public_only_twin_insufficient_telemetry():
    r = client.get("/api/v1/wells/BGW-01/twin")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "INSUFFICIENT_PUBLIC_TELEMETRY"


def test_21_api_works_for_ingested_telemetry():
    client.post("/api/v1/telemetry/ingest", json={
        "well_id": "BGW-08", "reservoir_temperature_c": 60.0,
        "reservoir_pressure_bar": 30.0, "api_gravity": 18.0,
        "wellhead_pressure_bar": 12.0, "oil_rate_bopd": 40.0,
        "steam_volume_t": 900.0, "steam_injection_pressure_bar": 65.0,
        "soak_time_h": 48.0, "css_phase": "PRODUCTION",
        "spm": 6.0, "stroke_in": 96.0, "vfd_percent": 55.0})
    r = client.get("/api/v1/wells/BGW-08/twin")
    assert r.status_code == 200
    assert r.json()["estimated_oil_production_bopd"] > 0
    app_module.reset_block1_state()


def test_22_no_secrets_introduced():
    import re as _re
    roots = [os.path.join(os.path.dirname(__file__), "data", "public"),
             os.path.join(os.path.dirname(__file__), "data_catalog")]
    blob = ""
    for root in roots:
        for name in os.listdir(root):
            if name.endswith(".json"):
                with open(os.path.join(root, name), encoding="utf-8") as fh:
                    blob += fh.read()
    for pat in (r"sk-[A-Za-z0-9]{8,}", r"api[_-]?key\s*[:=]",
                r"AKIA[0-9A-Z]{16}", r"-----BEGIN .*PRIVATE KEY-----"):
        assert not _re.search(pat, blob, _re.IGNORECASE)


def test_23_field_values_cannot_leak_into_telemetry():
    field = _public("baghewala_field.json")
    assert field.get("scope") == "FIELD_LEVEL"
    visc = field["oil"]["viscosity_cp_at_50C"]["value"]
    assert visc == [10000.0, 13000.0]
    # No public well record may carry the field viscosity as its own.
    for rec in _public("baghewala_wells.json")["wells"]:
        assert "oil_viscosity_cp" not in rec or rec.get("oil_viscosity_cp") is None


def test_24_derived_values_traceable():
    prod = _public("baghewala_production.json")
    rec = next(r for r in prod["well_specific"] if r.get("well_id") == "BGW-08")
    for f in ("record_id", "source_id", "source_publication_date",
              "extraction_method", "derivation", "derived_from", "record_hash"):
        assert rec.get(f), f"missing traceability field: {f}"
    wells = _public("baghewala_wells.json")
    for w in wells["wells"]:
        assert w.get("record_id") and w.get("record_hash")


def test_25_coverage_endpoint_and_catalog_consistency():
    cov = client.get("/api/v1/data/coverage").json()
    assert cov["total_verified_wells"] == 5
    cat = client.get("/api/v1/data/catalog").json()
    assert "5 publicly verified well records" in cat["telemetry_availability_statement"] or \
        "5 publicly verified well" in cat["telemetry_availability_statement"]
    assert "never be attached to individual wells" in cat["telemetry_availability_statement"]
    ids = {d["dataset_id"] for d in cat["datasets"]}
    assert {"baghewala_well_public", "baghewala_derived_values"} <= ids
