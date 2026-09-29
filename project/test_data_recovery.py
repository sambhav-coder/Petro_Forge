"""Priority 1 recovery tests: verified public Baghewala registry.

Covers Objective 30: registry load, bootstrap, non-empty wells without
seeding, BAGHEWALA_FIELD provenance, historical dates, no field-to-well
attribution, synthetic separation, no LIVE upgrade, null telemetry,
conflict traceability, invalid rejection, telemetry/twin compat,
summary provenance, coverage match.
"""

import importlib.util
import json
import os

import pytest
from fastapi.testclient import TestClient

from data.bootstrap import bootstrap_public_data

app_path = os.path.join(os.path.dirname(__file__), "app.py")
spec = importlib.util.spec_from_file_location("app_sih26120_recovery", app_path)
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)
app = app_module.app
client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean():
    app_module.reset_block1_state()
    app_module.DATA_REPO._telemetry.clear()
    app_module.DATA_REPO._wells.clear()
    app_module.DATA_REPO._cycles.clear()
    app_module.DATA_QUALITY_LOG.clear()
    yield


def public_root():
    return os.path.join(os.path.dirname(__file__), "data", "public")


def test_1_registry_files_load_and_validate():
    report = bootstrap_public_data()["report"]
    assert report["public_wells"] == 5
    assert report["public_css_records"] == 2
    assert report["rejected_records"] == 0


def test_2_verified_well_ids():
    wells = bootstrap_public_data()["wells"]
    assert set(wells) == {"BGW-01", "BGW-04", "BGW-08", "BGW-17", "BGW-40"}


def test_3_bootstrap_report_counts():
    report = bootstrap_public_data()["report"]
    assert report["public_production_records"] == 7  # 1 well + 6 field
    assert report["synthetic_records"] == 0


def test_4_wells_nonempty_without_seeding():
    data = client.get("/api/v1/wells").json()
    assert data["total_wells"] == 5
    assert {w["well_id"] for w in data["wells"]} == {
        "BGW-01", "BGW-04", "BGW-08", "BGW-17", "BGW-40"}


def test_5_no_synthetic_seed_required():
    data = client.get("/api/v1/wells").json()
    assert all(w["data_status"] == "PUBLIC_FIELD_RECORD" for w in data["wells"])
    assert not any(w["well_id"].startswith("BGW-DEMO") for w in data["wells"])


def test_6_public_provenance():
    data = client.get("/api/v1/wells").json()
    assert all(w["provenance"] == "BAGHEWALA_FIELD" for w in data["wells"])


def test_7_historical_dates_retained():
    detail = client.get("/api/v1/wells/BGW-08").json()
    assert detail["data_status"] == "PUBLIC_FIELD_RECORD"
    assert detail["status_as_of"] == "2019-06-05"
    assert any("2018" in (c.get("injection_start") or "") for c in detail["css"])


def test_8_field_values_not_on_wells():
    # 1202 bopd is field-level: must not appear as any well's oil rate.
    data = client.get("/api/v1/wells").json()
    assert all(w["oil_rate_bopd"] != 1202.0 for w in data["wells"])
    bgw08 = client.get("/api/v1/wells/BGW-08").json()
    assert bgw08["telemetry"] is None
    assert bgw08["production"][0]["value"] == 85.0  # well-specific midpoint


def test_9_synthetic_stays_synthetic():
    from data import synthetic as syn
    recs = syn.generate(cycles_per_well=1, seed=5, include_bad=False)
    assert all(r["provenance"] == "SYNTHETIC_BAGHEWALA" for r in recs)
    assert "BGW-08" not in {r["well_id"] for r in recs}


def test_10_public_not_live():
    bgw08 = client.get("/api/v1/wells/BGW-08").json()
    assert bgw08["data_status"] == "PUBLIC_FIELD_RECORD"
    assert "LIVE" not in bgw08["data_status"]
    r = client.get("/api/v1/wells/BGW-08/twin")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "INSUFFICIENT_PUBLIC_TELEMETRY"


def test_11_unknown_telemetry_null():
    bgw40 = client.get("/api/v1/wells/BGW-40").json()
    assert bgw40["telemetry"] is None
    assert bgw40["status"] == "UNKNOWN"


def test_12_conflicts_traceable():
    with open(os.path.join(os.path.dirname(__file__), "data_catalog",
                           "provenance.json"), encoding="utf-8") as fh:
        values = json.load(fh)["values"]
    conflicted = [v for v in values if "conflict" in v]
    assert len(conflicted) >= 2  # area, well counts, field rates
    assert all("source_id" in v and ("provenance" in v or "provenance_class" in v)
               for v in values)
    with open(os.path.join(os.path.dirname(__file__), "data_catalog",
                           "value_provenance.json"), encoding="utf-8") as fh:
        recs = json.load(fh)["records"]
    assert all("source_id" in r and "provenance" in r and "confidence" in r for r in recs)


def test_13_invalid_public_records_rejected():
    from data.bootstrap import _valid_well, _valid_css
    assert not _valid_well({"well_id": "", "field": "x", "provenance": "BAGHEWALA_FIELD"})[0]
    assert not _valid_well({"well_id": "BGW-99"})[0]
    assert not _valid_css({"cycle_id": "C", "well_id": "BGW-08", "provenance": "NOPE"})[0]
    assert _valid_well({"well_id": "BGW-08", "field": "Baghewala",
                        "provenance": "BAGHEWALA_FIELD"})[0]


def test_14_telemetry_compat_preserved():
    r = client.post("/api/v1/telemetry/ingest", json={
        "well_id": "BGW-08", "reservoir_temperature_c": 60.0,
        "reservoir_pressure_bar": 30.0, "api_gravity": 18.0,
        "wellhead_pressure_bar": 12.0, "oil_rate_bopd": 40.0,
        "steam_volume_t": 900.0, "steam_injection_pressure_bar": 65.0,
        "soak_time_h": 48.0, "css_phase": "PRODUCTION",
        "spm": 6.0, "stroke_in": 96.0, "vfd_percent": 55.0})
    assert r.status_code == 201
    # Telemetry supersedes public record in list + detail.
    wells = {w["well_id"]: w for w in client.get("/api/v1/wells").json()["wells"]}
    assert wells["BGW-08"]["data_status"] == "LIVE_TELEMETRY"
    assert wells["BGW-08"]["oil_rate_bopd"] == 40.0
    assert client.get("/api/v1/wells/BGW-08").json()["oil_rate_bopd"] == 40.0


def test_15_twin_compat_preserved():
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


def test_16_summary_provenance_and_status():
    s = client.get("/api/v1/data/summary").json()
    assert s["public_registry"]["public_wells"] == 5
    assert s["public_registry"]["public_css_records"] == 2
    assert s["data_status"]["public_field_records"] == 5
    assert s["data_status"]["public_telemetry_records"] == 0
    assert s["data_status"]["synthetic_records"] == 0


def test_17_coverage_matches_registry():
    with open(os.path.join(os.path.dirname(__file__), "data_catalog",
                           "baghewala_well_coverage.json"), encoding="utf-8") as fh:
        cov = json.load(fh)
    wells = bootstrap_public_data()["wells"]
    assert cov["total_verified_wells"] == len(wells) == 5
    assert {w["well_id"] for w in cov["wells"]} == set(wells)
    assert all(w["telemetry_data"] is False for w in cov["wells"])


def test_18_unknown_well_still_404():
    assert client.get("/api/v1/wells/BGW-UNKNOWN").status_code == 404
    r = client.get("/api/v1/wells/BGW-UNKNOWN/twin")
    assert r.status_code == 404
    assert isinstance(r.json()["detail"], str)
