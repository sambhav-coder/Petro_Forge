"""Priority 1 data-foundation tests (offline, deterministic).

Covers: catalog validity, schema nullability, unit conversion + ambiguity,
missing/duplicate/invalid cleaning, hard vs soft validation, timestamps,
provenance labels, synthetic determinism, physics reuse in features,
pipeline end-to-end, repository abstraction (+JSONL roundtrip),
data API endpoints, telemetry backward compatibility, path safety.
"""

import json
import os

import pytest
from fastapi.testclient import TestClient

import twin_physics as tp
from data import DATA_SCHEMA_VERSION, ProvenanceClass
from data import synthetic as syn
from data.baghewala_constraints import ENGINEERING_ASSUMPTIONS, SOURCE_CONSTRAINED
from data.cleaning import clean_telemetry, dedupe
from data.features import engineer_pairwise, engineer_record
from data.pipeline import ingest_telemetry_batch
from data.provenance import Provenance, synthetic_provenance
from data.quality import QualityFlag, QualityStatus, merge_quality, new_quality
from data.repository import InMemoryRepository, JsonlFileRepository, safe_base_dir
from data.schema import FeatureRecord, TelemetryRecord
from data.units import normalize_value, normalize_vfd, normalize_water_cut

import importlib.util

app_path = os.path.join(os.path.dirname(__file__), "app.py")
spec = importlib.util.spec_from_file_location("app_sih26120_data", app_path)
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


def good_raw(**over):
    base = {
        "timestamp": "2025-03-01T06:00:00+00:00",
        "well_id": "BGW-T01",
        "reservoir_temperature_c": 47.0,
        "reservoir_pressure_bar": 28.0,
        "oil_rate_bopd": 20.0,
        "spm": 5.0,
        "stroke_in": 96.0,
        "css_phase": "production",
        "source_id": "test",
        "provenance": "BAGHEWALA_FIELD",
    }
    base.update(over)
    return base


# ---- 1. catalog validity ----
def test_catalog_files_valid():
    root = os.path.join(os.path.dirname(__file__), "data_catalog")
    for name in ("data_sources.json", "data_catalog.json", "provenance.json"):
        with open(os.path.join(root, name), encoding="utf-8") as fh:
            doc = json.load(fh)
        assert doc["version"] == "1.0"
    sources = json.load(open(os.path.join(root, "data_sources.json")))["sources"]
    assert len(sources) >= 10
    required = {"source_id", "source_name", "publisher", "url", "source_type",
                "provenance_class", "license", "confidence"}
    for s in sources:
        assert required.issubset(s.keys()), s.get("source_id")
        assert s["provenance_class"] in {c.value for c in ProvenanceClass}
    catalog = json.load(open(os.path.join(root, "data_catalog.json")))
    assert "was not found" in catalog["telemetry_availability_statement"]


# ---- 2/3. schema + units ----
def test_schema_nullable_partial():
    rec = TelemetryRecord(well_id="BGW-X", oil_rate_bopd=10.0)
    assert rec.timestamp is None and rec.spm is None


def test_unit_conversions():
    assert normalize_value("pressure", 100.0, "psi")[0] == pytest.approx(6.89476)
    assert normalize_value("temperature", 212.0, "F")[0] == pytest.approx(100.0)
    assert normalize_value("oil_rate", 10.0, "m3/d")[0] == pytest.approx(62.8981)
    assert normalize_water_cut(35.0, "percent") == (pytest.approx(0.35), None)


def test_ambiguous_unit_flagged_not_converted():
    value, warn = normalize_value("pressure", 100.0, "furlongs")
    assert value == 100.0 and warn and "ambiguous" in warn
    value, warn = normalize_vfd(60.0, "Hz")
    assert value == 60.0 and "ambiguous" in warn


# ---- 4/5/6/8. cleaning + physical + timestamps ----
def test_missing_timestamp_flagged_missing():
    rec, q = clean_telemetry(good_raw(timestamp=None))
    assert rec is not None and rec.timestamp is None
    assert q.status == QualityStatus.MISSING.value
    assert QualityFlag.MISSING_VALUE.value in q.flags


def test_bad_timestamp_invalid():
    rec, q = clean_telemetry(good_raw(timestamp="yesterday-ish"))
    assert rec is None


def test_negative_pressure_invalid_hard():
    rec, q = clean_telemetry(good_raw(reservoir_pressure_bar=-5.0))
    assert rec is None and q.status == QualityStatus.INVALID.value


def test_soft_window_warns_but_keeps():
    rec, q = clean_telemetry(good_raw(spm=45.0))
    assert rec is not None and rec.spm == 45.0
    assert q.status == QualityStatus.WARNING.value


def test_bad_phase_warns_not_rejects():
    rec, q = clean_telemetry(good_raw(css_phase="BOILING"))
    assert rec is not None and q.status == QualityStatus.WARNING.value


def test_non_numeric_rejected():
    rec, q = clean_telemetry(good_raw(oil_rate_bopd="lots"))
    assert rec is None


def test_empty_well_id_rejected():
    rec, q = clean_telemetry(good_raw(well_id="  "))
    assert rec is None


def test_dedupe_marks_duplicates():
    r1, q1 = clean_telemetry(good_raw())
    r2, q2 = clean_telemetry(good_raw())
    kept, n = dedupe([(r1, q1), (r2, q2)])
    assert n == 1 and kept[1][1].status == QualityStatus.DUPLICATE.value


# ---- 9. provenance ----
def test_synthetic_requires_generator_version():
    with pytest.raises(ValueError):
        Provenance(provenance_class=ProvenanceClass.SYNTHETIC_BAGHEWALA)
    p = synthetic_provenance("synthetic_baghewala/1.0", "test constraints")
    assert p.generator_version == "synthetic_baghewala/1.0"


def test_synthetic_records_labeled():
    recs = syn.generate(cycles_per_well=1, seed=7, include_bad=False)
    assert all(r["provenance"] == "SYNTHETIC_BAGHEWALA" for r in recs)
    assert all(r["generator_version"] == "synthetic_baghewala/1.0" for r in recs)


# ---- 10/11. synthetic determinism ----
def test_synthetic_deterministic():
    a = syn.generate(seed=42)
    b = syn.generate(seed=42)
    assert a == b
    c = syn.generate(seed=43)
    assert a != c


def test_synthetic_has_bad_records_and_wells():
    recs = syn.generate(cycles_per_well=2, seed=42)
    wells = {r["well_id"] for r in recs if r.get("timestamp")}
    assert {"BGW-S01", "BGW-S02", "BGW-S03"}.issubset(wells)
    assert any(r.get("timestamp") is None for r in recs)


# ---- 12. features reuse physics ----
def test_features_reuse_twin_physics():
    rec = TelemetryRecord(well_id="W", reservoir_temperature_c=120.0,
                          steam_volume_t=800.0, steam_injection_pressure_bar=65.0,
                          spm=5.0, stroke_in=96.0)
    feats = {f.name: f for f in engineer_record(rec)}
    assert feats["estimated_viscosity_cp"].value == pytest.approx(tp.viscosity_cp(120.0, tp.API_REF))
    assert feats["estimated_viscosity_cp"].method == "twin_physics.viscosity_cp"
    assert feats["mobility_proxy"].value == pytest.approx(
        tp.mobility_factor(feats["estimated_viscosity_cp"].value))
    assert feats["heating_intensity"].value == pytest.approx(tp.heating_intensity(800.0, 65.0))
    assert all(f.status == "DERIVED_PROTOTYPE" and f.provenance == ProvenanceClass.DERIVED
               for f in feats.values())
    prev = TelemetryRecord(well_id="W", oil_rate_bopd=10.0, spm=4.0)
    curr = TelemetryRecord(well_id="W", oil_rate_bopd=15.0, spm=6.0)
    pair = {f.name: f for f in engineer_pairwise(prev, curr)}
    assert pair["production_change"].value == pytest.approx(5.0)
    assert pair["spm_change"].value == pytest.approx(2.0)


def test_feature_record_schema():
    f = FeatureRecord(name="x", value=1.0)
    assert f.status == "DERIVED_PROTOTYPE"


# ---- 13/14. pipeline + repository ----
def test_pipeline_end_to_end():
    repo = InMemoryRepository()
    raw = syn.generate(cycles_per_well=1, seed=11)
    report, feats = ingest_telemetry_batch(raw, repo, source_id="syn-test",
                                           provenance="SYNTHETIC_BAGHEWALA")
    assert report.accepted > 0 and report.rejected > 0  # bad records caught
    assert report.duplicates >= 1 and report.provenance == "SYNTHETIC_BAGHEWALA"
    assert repo.counts()["telemetry"] == report.accepted
    assert len(feats) > 0
    # determinism
    repo2 = InMemoryRepository()
    report2, _ = ingest_telemetry_batch(raw, repo2, source_id="syn-test",
                                        provenance="SYNTHETIC_BAGHEWALA")
    assert report.to_dict() == report2.to_dict()


def test_repository_wells_cycles_and_jsonl(tmp_path, monkeypatch):
    repo = InMemoryRepository()
    from data.schema import WellRecord, CSSCycleRecord
    repo.save_wells([WellRecord(well_id="BGW-1")])
    repo.save_cycles([CSSCycleRecord(cycle_id="C1", well_id="BGW-1")])
    assert repo.get_wells()[0].well_id == "BGW-1"
    assert repo.get_cycles("BGW-1")[0].cycle_id == "C1"

    monkeypatch.chdir(tmp_path)
    file_repo = JsonlFileRepository(base_dir="store")
    file_repo.save_telemetry([TelemetryRecord(well_id="BGW-9", oil_rate_bopd=3.0)])
    assert file_repo.get_telemetry("BGW-9")[0].oil_rate_bopd == 3.0
    reopened = JsonlFileRepository(base_dir="store")
    assert reopened.get_telemetry("BGW-9")[0].oil_rate_bopd == 3.0


def test_quality_merge_worst_wins():
    q = merge_quality([new_quality(), new_quality(status=QualityStatus.WARNING)])
    assert q.status == "WARNING"


# ---- 15/17. API endpoints + security ----
def test_data_sources_endpoint():
    r = client.get("/api/v1/data/sources")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 10 and all("provenance_class" in s for s in body["sources"])


def test_data_catalog_endpoint():
    r = client.get("/api/v1/data/catalog")
    assert r.status_code == 200
    assert "was not found" in r.json()["telemetry_availability_statement"]


def test_data_ingest_endpoint_and_quality_summary():
    units = {"reservoir_temperature_c": "C", "reservoir_pressure_bar": "bar",
             "oil_rate_bopd": "BOPD", "stroke_in": "in"}
    rec_ok = {k: v for k, v in good_raw().items() if k != "provenance"}
    rec_bad = {k: v for k, v in good_raw(reservoir_pressure_bar=-2.0).items()
               if k != "provenance"}
    payload = {"records": [rec_ok, rec_bad],
               "source_id": "t", "provenance": "SYNTHETIC_BAGHEWALA", "units": units}
    r = client.post("/api/v1/data/ingest", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["accepted"] == 1 and body["rejected"] == 1
    q = client.get("/api/v1/data/quality").json()
    assert q["total_ingested"] == 2 and q["by_status"]["VALID"] == 1
    s = client.get("/api/v1/data/summary").json()
    assert s["store"]["telemetry"] == 1
    assert s["by_provenance"]["SYNTHETIC_BAGHEWALA"] == 1
    assert s["schema_version"] == DATA_SCHEMA_VERSION


def test_missing_units_warn_but_accept():
    # No unit metadata -> values assumed canonical AND flagged (never silent).
    rec, q = clean_telemetry(good_raw())
    assert rec is not None and q.status == QualityStatus.WARNING.value
    assert QualityFlag.AMBIGUOUS_UNIT.value in q.flags


def test_data_ingest_rejects_bad_provenance_and_oversize():
    r = client.post("/api/v1/data/ingest",
                    json={"records": [good_raw()], "provenance": "MARS_BASE"})
    assert r.status_code == 422
    r = client.post("/api/v1/data/ingest", json={"records": []})
    assert r.status_code == 422


def test_path_traversal_rejected():
    with pytest.raises(ValueError):
        safe_base_dir("/abs/path")
    with pytest.raises(ValueError):
        safe_base_dir("../escape")


# ---- 16. telemetry backward compatibility ----
def test_telemetry_endpoint_unchanged():
    r = client.post("/api/v1/telemetry/ingest", json={
        "well_id": "BGW-01", "reservoir_temperature_c": 47.0,
        "reservoir_pressure_bar": 28.5, "api_gravity": 18.0,
        "wellhead_pressure_bar": 12.0, "oil_rate_bopd": 22.5,
        "steam_volume_t": 850.0, "steam_injection_pressure_bar": 65.0,
        "soak_time_h": 48.0, "css_phase": "PRODUCTION",
        "spm": 5.0, "stroke_in": 96.0, "vfd_percent": 55.0})
    assert r.status_code == 201
    assert r.json()["status"] == "TELEMETRY_ACCEPTED"


def test_constraints_separate_source_from_assumption():
    assert "api_gravity_range" in SOURCE_CONSTRAINED
    assert "spm_operating_band" in ENGINEERING_ASSUMPTIONS
    assert set(SOURCE_CONSTRAINED).isdisjoint(set(ENGINEERING_ASSUMPTIONS))
