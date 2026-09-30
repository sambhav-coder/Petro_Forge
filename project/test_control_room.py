"""P8 Control Room integration tests: shared well context, overview,
hybrid summary, insufficiency/synthetic labels, SRP/CSS summaries, alerts
+ ack, unavailable states, sourced recommendations, explicit optimization,
and endpoint stability across the operator workflow."""

import importlib.util
import os

import pytest
from fastapi.testclient import TestClient

app_path = os.path.join(os.path.dirname(__file__), "app.py")
spec = importlib.util.spec_from_file_location("app_sih26120_controlroom", app_path)
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)
client = TestClient(app_module.app)


@pytest.fixture(autouse=True)
def _clean():
    app_module.reset_block1_state()
    yield
    app_module.reset_block1_state()


def _payload(well="BGW-01", **over):
    d = dict(
        well_id=well, reservoir_temperature_c=60.0,
        reservoir_pressure_bar=30.0, api_gravity=18.0,
        wellhead_pressure_bar=12.0, oil_rate_bopd=40.0, steam_volume_t=900.0,
        steam_injection_pressure_bar=65.0, soak_time_h=48.0,
        css_phase="PRODUCTION", spm=6.0, stroke_in=96.0, vfd_percent=55.0,
    )
    d.update(over)
    return d


def _ingest(well="BGW-01", **over):
    r = client.post("/api/v1/telemetry/ingest", json=_payload(well, **over))
    assert r.status_code == 201
    return r.json()


# 1. Selected well context is preserved across endpoints.
def test_1_well_context_preserved():
    _ingest("BGW-01")
    _ingest("BGW-02", spm=7.0)
    assert client.get("/api/v1/wells/BGW-01").json()["spm"] == 6.0
    assert client.get("/api/v1/wells/BGW-02").json()["spm"] == 7.0
    assert client.get("/api/v1/wells/BGW-01/twin").json()["spm"] == 6.0
    assert client.get("/api/v1/wells/BGW-02/twin").json()["spm"] == 7.0


# 2. Field overview data is consumed correctly.
def test_2_field_overview_shape():
    _ingest("BGW-01")
    ov = client.get("/api/v1/field/overview").json()
    for f in ("total_wells", "producing_wells", "field_oil_rate_bopd",
              "by_phase", "live"):
        assert f in ov
    assert ov["total_wells"] >= 1


# 3. Hybrid Twin summary consumes the canonical endpoint.
def test_3_hybrid_summary_fields():
    _ingest("BGW-01")
    h = client.get("/api/v1/wells/BGW-01/twin/hybrid").json()
    for f in ("observed", "physics", "calibration", "divergence",
              "diagnostics", "ml_evidence", "recommendations",
              "provenance", "uncertainty"):
        assert f in h


# 4. Insufficient-data state displayed correctly (public-only well).
def test_4_insufficient_data_honest():
    r = client.get("/api/v1/wells/BGW-08/twin/hybrid")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "INSUFFICIENT_PUBLIC_TELEMETRY"
    d = client.get("/api/v1/wells/BGW-08").json()
    assert d["data_status"] == "PUBLIC_FIELD_RECORD"
    assert d["telemetry"] is None


# 5. Synthetic ML is labelled synthetic.
def test_5_synthetic_ml_labelled():
    _ingest("BGW-01")
    body = client.get("/api/v1/wells/BGW-01/predict").json()
    assert body["mode"] == "SYNTHETIC"
    assert body["production_safe"] is False
    h = client.get("/api/v1/wells/BGW-01/twin/hybrid").json()
    assert h["ml_evidence"]["mode"] == "SYNTHETIC"


# 6-7. SRP / CSS summaries consume existing endpoints.
def test_6_srp_summary_endpoint():
    _ingest("BGW-01")
    body = client.get("/api/v1/wells/BGW-01/dynacard").json()
    assert "pprl_lb" in body and "pump_performance" in body
    assert body["pump_performance"]["efficiency"]["status"] in (
        "CALCULATED", "UNAVAILABLE", "INVALID")


def test_7_css_summary_endpoint():
    _ingest("BGW-01")
    assert "optimal_cutoff_production_day" in \
        client.get("/api/v1/wells/BGW-01/cycle").json()
    multi = client.post("/api/v1/wells/BGW-01/cycle/multi",
                        json={"cycles": 1}).json()
    assert multi["recommendation"]["next_cycle_number"] == 2


# 8-9. Alerts displayed + acknowledgement available.
def test_8_alerts_from_api():
    _ingest("BGW-01", spm=12.0, stroke_in=144.0, steam_volume_t=0.0,
            steam_injection_pressure_bar=0.0)
    alerts = client.get("/api/v1/alerts?limit=50").json()
    assert alerts["total"] >= 1
    first = alerts["alerts"][0]
    for f in ("alert_id", "well_id", "type", "severity", "title",
              "detail", "timestamp", "acknowledged"):
        assert f in first
    assert first["severity"] in ("HIGH", "MODERATE", "LOW")


def test_9_acknowledgement_works():
    _ingest("BGW-01", spm=12.0, stroke_in=144.0, steam_volume_t=0.0,
            steam_injection_pressure_bar=0.0)
    alerts = client.get("/api/v1/alerts?limit=50").json()["alerts"]
    assert alerts, "stressed fixture must raise at least one alert"
    aid = alerts[0]["alert_id"]
    assert client.post(f"/api/v1/alerts/{aid}/ack").status_code in (200, 201)
    again = client.get("/api/v1/alerts?limit=50").json()["alerts"]
    assert [a for a in again if a["alert_id"] == aid][0]["acknowledged"] is True


# 10. API unavailable state does not fabricate data.
def test_10_unknown_well_no_fabrication():
    r = client.get("/api/v1/wells/BGW-NOPE")
    assert r.status_code == 404
    assert client.get("/api/v1/wells/BGW-NOPE/twin").status_code == 404
    assert client.get("/api/v1/wells/BGW-NOPE/twin/hybrid").status_code == 404


# 11-12. Historical / synthetic labels preserved.
def test_11_historical_labelled():
    cov = client.get("/api/v1/history/coverage/BGW-08").json()
    assert cov["well_id"] == "BGW-08"
    hist = client.get("/api/v1/history?well_id=BGW-08&limit=10").json()
    assert hist["count"] >= 0
    for o in hist.get("observations", []):
        assert o["data_status"] != "LIVE_TELEMETRY" or o["provenance"] != "BAGHEWALA_FIELD"


def test_12_synthetic_demo_labelled():
    _ingest("BGW-DEMO")
    h = client.get("/api/v1/wells/BGW-DEMO/twin/hybrid").json()
    assert h["data_status"] == "SYNTHETIC_DEMO"
    assert h["provenance"]["observed_provenance"] == "SYNTHETIC_BAGHEWALA"


# 13. Recommendations retain their source.
def test_13_recommendation_sources():
    _ingest("BGW-01")
    h = client.get("/api/v1/wells/BGW-01/twin/hybrid").json()
    assert all("source" in r and "text" in r for r in h["recommendations"])
    opt = client.post("/api/v1/wells/BGW-01/optimize", json={}).json()
    assert opt["why_recommended"] and opt["recommendation_policy"]


# 14. Optimization is explicit, not auto-triggered.
def test_14_no_auto_optimization():
    _ingest("BGW-01")
    assert client.get("/api/v1/wells/BGW-01/optimize").status_code == 405
    twin = client.get("/api/v1/wells/BGW-01/twin").json()
    assert "score" not in twin


# 15-18. Endpoint stability across the workflow.
def test_15_hybrid_endpoint_stable():
    _ingest("BGW-01")
    h = client.get("/api/v1/wells/BGW-01/twin/hybrid").json()
    assert h["mode"] == "HYBRID_PROTOTYPE_TWIN"
    assert h["uncertainty"]["status"] == "UNAVAILABLE"


def test_16_srp_api_stable():
    _ingest("BGW-01")
    body = client.get("/api/v1/wells/BGW-01/dynacard").json()
    assert body["primary_diagnosis"]
    assert body["pump_performance"]["mode"] == "PROTOTYPE_PHYSICS"


def test_17_css_api_stable():
    _ingest("BGW-01")
    plan = client.post("/api/v1/wells/BGW-01/cycle/plan", json={}).json()
    assert plan["recommended"]["steam_volume_t"] > 0


def test_18_optimizer_api_stable():
    _ingest("BGW-01")
    body = client.post("/api/v1/wells/BGW-01/optimize", json={}).json()
    assert body["pareto_count"] >= 1
    assert body["scenarios_evaluated"] == 243
