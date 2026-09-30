"""P4 Hybrid Twin tests: physics-first assembly, sufficiency states,
calibration honesty, divergence, ML separation, provenance, uncertainty,
regressions across SRP/CSS/optimizer/ML/live/SSE contracts."""

import importlib.util
import os

import pytest
from fastapi.testclient import TestClient

import hybrid_twin

app_path = os.path.join(os.path.dirname(__file__), "app.py")
spec = importlib.util.spec_from_file_location("app_sih26120_hybrid", app_path)
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)
client = TestClient(app_module.app)


@pytest.fixture(autouse=True)
def _clean():
    app_module.reset_block1_state()
    yield
    app_module.reset_block1_state()


def _payload(**over):
    d = dict(
        well_id="BGW-01", reservoir_temperature_c=60.0,
        reservoir_pressure_bar=30.0, api_gravity=18.0,
        wellhead_pressure_bar=12.0, oil_rate_bopd=40.0, steam_volume_t=900.0,
        steam_injection_pressure_bar=65.0, soak_time_h=48.0,
        css_phase="PRODUCTION", spm=6.0, stroke_in=96.0, vfd_percent=55.0,
    )
    d.update(over)
    return d


def _ingest(n=1, **over):
    for _ in range(n):
        r = client.post("/api/v1/telemetry/ingest", json=_payload(**over))
        assert r.status_code == 201


def _hybrid():
    r = client.get("/api/v1/wells/BGW-01/twin/hybrid")
    assert r.status_code == 200, r.text[:300]
    return r.json()


# 1. Valid telemetry produces a physics prediction.
def test_1_physics_prediction_present():
    _ingest()
    h = _hybrid()
    assert h["physics"]["status"] == "CALCULATED"
    assert h["physics"]["mode"] == "PROTOTYPE_PHYSICS"
    assert h["physics"]["prediction"]["oil_production_bopd"] > 0
    assert h["observed"]["oil_rate_bopd"] == 40.0


# 2. Missing data (public-only well) -> explicit insufficient state.
def test_2_public_only_insufficient():
    r = client.get("/api/v1/wells/BGW-08/twin/hybrid")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "INSUFFICIENT_PUBLIC_TELEMETRY"
    assert client.get("/api/v1/wells/BGW-NOPE/twin/hybrid").status_code == 404


# 3-4. Calibration only with sufficient data; never fabricated.
def test_3_calibration_insufficient_with_one_reading():
    _ingest()
    h = _hybrid()
    assert h["calibration"]["status"] == "INSUFFICIENT_DATA"
    assert h["calibration"]["factor"] is None
    assert h["calibrated_prediction"] is None


def test_4_calibration_with_three_readings():
    _ingest(3)
    h = _hybrid()
    assert h["calibration"]["status"] == "CALIBRATED"
    assert isinstance(h["calibration"]["factor"], float)
    assert h["calibration"]["observations"] >= 3


# 5-6. Raw vs calibrated predictions distinguishable.
def test_5_raw_prediction_accessible():
    _ingest(3)
    h = _hybrid()
    assert h["physics"]["prediction"]["oil_production_bopd"] > 0
    assert h["calibrated_prediction"]["factor"] == h["calibration"]["factor"]


def test_6_calibrated_differs_by_factor():
    _ingest(3)
    h = _hybrid()
    raw = h["physics"]["prediction"]["oil_production_bopd"]
    cal = h["calibrated_prediction"]["oil_production_bopd"]
    assert cal == pytest.approx(h["calibration"]["factor"] * raw, rel=1e-3)


# 7-8. Divergence computed / unavailable correctly.
def test_7_divergence_calculated_with_history():
    _ingest()
    h = _hybrid()
    assert h["divergence"]["status"] == "CALCULATED"
    assert h["divergence"]["severity"] in ("TRACKING", "WATCH", "DIVERGED")
    assert h["divergence"]["baseline"] == "raw_physics"


def test_8_divergence_uses_calibrated_baseline_when_available():
    _ingest(3)
    h = _hybrid()
    assert h["divergence"]["baseline"] == "calibrated"


# 9-10. ML evidence separate + synthetic labeled.
def test_9_ml_evidence_separate_from_physics():
    _ingest()
    h = _hybrid()
    assert "predictions" not in h["physics"]
    assert "probability" not in h["physics"]
    assert h["ml_evidence"]["status"] == "ATTACHED_SEPARATE_EVIDENCE"


def test_10_synthetic_ml_labeled():
    _ingest()
    h = _hybrid()
    assert h["ml_evidence"]["mode"] == "SYNTHETIC"
    assert h["ml_evidence"]["production_safe"] is False
    assert set(h["ml_evidence"]["predictions"]) == {"rod_failure", "pump_unsetting"}


# 11-12. No fabricated uncertainty; provenance preserved.
def test_11_uncertainty_unavailable():
    _ingest(3)
    h = _hybrid()
    assert h["uncertainty"]["status"] == "UNAVAILABLE"
    blob = str(h["calibration"]) + str(h["divergence"]) + str(h["physics"])
    assert "confidence_interval" not in blob
    assert "prediction_interval" not in blob


def test_12_provenance_preserved():
    _ingest()
    h = _hybrid()
    assert h["data_status"] == "LIVE_TELEMETRY"
    assert h["provenance"]["physics_mode"] == "PROTOTYPE_PHYSICS"
    assert h["provenance"]["ml_mode"] == "SYNTHETIC"
    _ingest(0)  # no-op guard
    assert h["mode"] == "HYBRID_PROTOTYPE_TWIN"


# 13-18. Regression: SRP / CSS / optimizer / ML / live+SSE / compat.
def test_13_srp_intact():
    _ingest()
    body = client.get("/api/v1/wells/BGW-01/dynacard").json()
    assert "pump_performance" in body and "pprl_lb" in body


def test_14_css_intact():
    _ingest()
    assert "optimal_cutoff_production_day" in \
        client.get("/api/v1/wells/BGW-01/cycle").json()
    multi = client.post("/api/v1/wells/BGW-01/cycle/multi", json={"cycles": 1}).json()
    assert multi["cumulative"]["cycles_simulated"] == 1


def test_15_optimizer_intact():
    _ingest()
    body = client.post("/api/v1/wells/BGW-01/optimize", json={}).json()
    assert body["pareto_count"] >= 1 and len(body["top_scenarios"]) == 5


def test_16_ml_endpoints_intact():
    assert client.get("/api/v1/ml/status").json()["status"] == "OPERATIONAL"
    fc = client.post("/api/v1/ml/forecast",
                     json={"well_id": "BGW-01", "horizon_days": 7}).json()
    assert fc["insufficient_data"] is True


def test_17_live_sse_intact():
    assert client.get("/api/v1/live/status").json()["running"] is False
    assert client.get("/api/v1/alerts?limit=5").status_code == 200
    assert client.get("/api/v1/field/overview").status_code == 200


def test_18_response_fields_stable():
    _ingest()
    h = _hybrid()
    for f in ("well_id", "mode", "data_status", "observed", "physics",
              "calibration", "calibrated_prediction", "divergence",
              "diagnostics", "ml_evidence", "recommendations",
              "provenance", "uncertainty", "prototype_disclaimer"):
        assert f in h
    assert isinstance(h["recommendations"], list) and len(h["recommendations"]) >= 1
    assert all("text" in r and "source" in r for r in h["recommendations"])
