"""P0 ML runtime unification tests: canonical ml/ path, synthetic safety,
shim delegation, registry hygiene, clean-tree guarantee."""

import importlib.util
import json
import os
import subprocess
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from ml import synthetic_hazard
from ml.registry import ModelRegistry
import ml_models  # deprecated shim under test

app_path = os.path.join(os.path.dirname(__file__), "app.py")
spec = importlib.util.spec_from_file_location("app_sih26120_ml_unify", app_path)
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)
client = TestClient(app_module.app)

HERE = os.path.dirname(os.path.abspath(__file__))
TRACKED_REGISTRY = os.path.join(HERE, "ml", "artifacts", "registry.json")


@pytest.fixture(autouse=True)
def _clean_state():
    app_module.reset_block1_state()
    yield
    app_module.reset_block1_state()


def _state(**over):
    d = dict(
        well_id="BGW-01", timestamp="2026-09-29T10:00:00+00:00",
        reservoir_temperature_c=47.0, reservoir_pressure_bar=28.5,
        api_gravity=18.0, wellhead_pressure_bar=12.0, oil_rate_bopd=22.5,
        steam_volume_t=850.0, steam_injection_pressure_bar=65.0,
        soak_time_h=48.0, css_phase="PRODUCTION", spm=5.0, stroke_in=96.0,
        vfd_percent=55.0, water_cut_percent=35.0, days_in_phase=0.0,
    )
    d.update(over)
    return SimpleNamespace(**d)


def _payload(**over):
    d = dict(
        well_id="BGW-01", reservoir_temperature_c=47.0,
        reservoir_pressure_bar=28.5, api_gravity=18.0,
        wellhead_pressure_bar=12.0, oil_rate_bopd=22.5, steam_volume_t=850.0,
        steam_injection_pressure_bar=65.0, soak_time_h=48.0,
        css_phase="PRODUCTION", spm=5.0, stroke_in=96.0, vfd_percent=55.0,
        water_cut_percent=35.0,
    )
    d.update(over)
    return d


# 1. Canonical ML runtime is used by live ingest.
def test_1_ingest_runs_canonical_predict():
    assert app_module.synthetic_hazard is synthetic_hazard
    r = client.post("/api/v1/telemetry/ingest", json=_payload())
    assert r.status_code == 201
    hist = app_module.HISTORY.get("BGW-01", [])
    assert len(hist) == 1
    assert "rod_failure_prob" in hist[0] and "pump_unsetting_prob" in hist[0]


# 2. Legacy ml_models is not directly used by live ingest.
def test_2_legacy_module_not_in_app_namespace():
    assert not hasattr(app_module, "ml_models")
    src = open(app_path, encoding="utf-8").read()
    assert "ml_models.predict" not in src
    assert "ml_models.model_info" not in src
    assert "ml_models.PROB_HIGH" not in src


# 3. Alerts consume canonical ML output with explicit synthetic mode.
def test_3_ml_alerts_carry_synthetic_mode():
    hot = _state(spm=12.0, stroke_in=144.0, steam_volume_t=0.0,
                 steam_injection_pressure_bar=0.0)
    pred = synthetic_hazard.predict(hot)
    snap = app_module.twin_physics.twin_snapshot(hot)
    card = app_module.srp_dynacard.dynacard(snap, hot.api_gravity)
    raised = app_module._evaluate_alerts(hot, snap, card, pred, [], None)
    ml_alerts = [a for a in raised if a["type"].startswith("ML_")]
    assert ml_alerts, "expected at least one ML alert on stressed state"
    assert all(a.get("model_mode") == "SYNTHETIC" for a in ml_alerts)


# 4. Synthetic provenance remains explicit end to end.
def test_4_predict_envelope_is_explicitly_synthetic():
    out = synthetic_hazard.predict(_state())
    assert out["mode"] == "SYNTHETIC"
    assert out["training_data"] == "synthetic"
    assert out["production_safe"] is False
    assert out["provenance"] == "synthetic"
    for name, p in out["predictions"].items():
        assert p["provenance"] == "synthetic"
        assert p["mode"] == "SYNTHETIC"
    info = synthetic_hazard.model_info()
    assert info["label_source"] == "SYNTHETIC_HAZARD_MODEL"
    assert info["mode"] == "SYNTHETIC"
    assert info["production_safe"] is False


# 5. ML API endpoints remain functional.
def test_5_ml_api_surface_functional():
    st = client.get("/api/v1/ml/status").json()
    assert st["status"] == "OPERATIONAL"
    models = client.get("/api/v1/ml/models").json()
    assert models["total"] == 0  # no demo entries in canonical registry
    assert models["models"] == []
    fc = client.post("/api/v1/ml/forecast",
                     json={"well_id": "BGW-01", "horizon_days": 7}).json()
    assert fc["insufficient_data"] is True


# 6. Compatibility shims route through canonical ML.
def test_6_legacy_shim_delegates_to_canonical():
    assert ml_models.predict is synthetic_hazard.predict
    assert ml_models.model_info is synthetic_hazard.model_info
    assert ml_models.PROB_HIGH == synthetic_hazard.PROB_HIGH
    r = client.get("/api/v1/wells/BGW-01/predict")
    assert r.status_code == 404  # no telemetry yet: shim still guards
    client.post("/api/v1/telemetry/ingest", json=_payload())
    body = client.get("/api/v1/wells/BGW-01/predict").json()
    assert body["mode"] == "SYNTHETIC"
    assert body["production_safe"] is False
    card = client.get("/api/v1/ml/model").json()
    assert card["label_source"] == "SYNTHETIC_HAZARD_MODEL"
    assert card["mode"] == "SYNTHETIC"


# 7. Test registry generation uses temporary paths (tracked file untouched).
def test_7_registry_writes_do_not_touch_repo():
    before = open(TRACKED_REGISTRY, encoding="utf-8").read()
    reg = ModelRegistry()
    assert "ml_artifacts" in reg.artifact_dir or "tmp" in reg.artifact_dir.lower() \
        or "Temp" in reg.artifact_dir
    assert os.path.abspath(reg.artifact_dir) != os.path.abspath(
        os.path.join(HERE, "ml", "artifacts"))
    reg.register_model(
        model_id="unify_probe", task="production_forecast", version="1.0",
        dataset_id="probe", dataset_version="1.0",
        feature_schema={"spm": "float"}, hyperparameters={},
        metrics={"mae": 1.0}, validation_metrics={"mae": 1.0},
        test_metrics={"mae": 1.0},
    )
    after = open(TRACKED_REGISTRY, encoding="utf-8").read()
    assert before == after
    assert json.loads(before) == {}


# 8. pytest leaves tracked files clean (no M/A/D entries).
def test_8_working_tree_has_no_tracked_modifications():
    repo = os.path.dirname(HERE)
    out = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True,
        text=True, timeout=60,
    )
    assert out.returncode == 0
    bad = [l for l in out.stdout.splitlines()
           if l and l[0] in "MAD" and "ml/artifacts" not in l
           and "project/project" not in l]
    assert bad == [], f"tracked modifications found: {bad}"
