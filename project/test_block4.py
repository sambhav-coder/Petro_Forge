"""Block 4 tests: water cut, production cooling, VFD, dynacard, CSS cycle,
analytics, ML models, alerts, live field and SSE stream."""

import importlib.util
import json
import math
import os
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

import analytics
import css_cycle
import live_field
import ml_models
import srp_dynacard as dc
import twin_physics as tp

app_path = os.path.join(os.path.dirname(__file__), "app.py")
spec = importlib.util.spec_from_file_location("app_sih26120_block4", app_path)
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)
client = TestClient(app_module.app)


@pytest.fixture(autouse=True)
def _clean_state():
    app_module.reset_block1_state()
    yield
    app_module.reset_block1_state()


BASE = {
    "well_id": "BGW-01", "timestamp": "2026-09-29T10:00:00+00:00",
    "reservoir_temperature_c": 47.0, "reservoir_pressure_bar": 28.5, "api_gravity": 18.0,
    "wellhead_pressure_bar": 12.0, "oil_rate_bopd": 22.5, "steam_volume_t": 850.0,
    "steam_injection_pressure_bar": 65.0, "soak_time_h": 48.0, "css_phase": "PRODUCTION",
    "spm": 5.0, "stroke_in": 96.0, "vfd_percent": 55.0, "water_cut_percent": 35.0,
}


def state(**over):
    d = dict(BASE, days_in_phase=0.0)
    d.update(over)
    return SimpleNamespace(**d)


def cold_fast():
    return state(steam_volume_t=0.0, steam_injection_pressure_bar=0.0, spm=8.0)


# ---------------- physics extensions ----------------

def test_water_cut_reduces_oil_not_liquid():
    lo = tp.twin_snapshot(state(water_cut_percent=10.0))
    hi = tp.twin_snapshot(state(water_cut_percent=60.0))
    assert hi["estimated_liquid_production_bpd"] == pytest.approx(lo["estimated_liquid_production_bpd"])
    assert hi["estimated_oil_production_bopd"] < lo["estimated_oil_production_bopd"]
    assert hi["estimated_water_production_bwpd"] > lo["estimated_water_production_bwpd"]


def test_production_cooling_over_days():
    day0 = tp.twin_snapshot(state(days_in_phase=0.0))
    day30 = tp.twin_snapshot(state(days_in_phase=30.0))
    day90 = tp.twin_snapshot(state(days_in_phase=90.0))
    assert day0["estimated_temperature_c"] > day30["estimated_temperature_c"] > day90["estimated_temperature_c"]
    assert day90["estimated_temperature_c"] >= BASE["reservoir_temperature_c"] - 1e-9
    assert day0["estimated_viscosity_cp"] < day90["estimated_viscosity_cp"]
    # days_in_phase only affects PRODUCTION.
    soak0 = tp.twin_snapshot(state(css_phase="SOAK"))
    soak30 = tp.twin_snapshot(state(css_phase="SOAK", days_in_phase=30.0))
    assert soak0["estimated_temperature_c"] == soak30["estimated_temperature_c"]


def test_vfd_spm_mapping_roundtrip():
    for spm in (0.0, 2.5, 5.0, 10.0):
        assert tp.spm_for_vfd(tp.vfd_for_spm(spm)) == pytest.approx(spm, abs=0.01)
    assert tp.vfd_for_spm(50.0) == 100.0  # clamped
    assert tp.twin_snapshot(state(spm=5.0))["vfd_setpoint_percent"] == pytest.approx(50.0)


def test_fillage_drops_when_pump_outruns_inflow():
    ok = tp.twin_snapshot(state(spm=4.0))
    over = tp.twin_snapshot(cold_fast())
    assert 0.0 <= over["estimated_pump_fillage"] < ok["estimated_pump_fillage"] <= 1.0


# ---------------- dynacard ----------------

def test_dynacard_shape_and_loads():
    snap = tp.twin_snapshot(state())
    card = dc.dynacard(snap, 18.0)
    assert len(card["points"]) == dc.CARD_POINTS
    xs = [p["position_in"] for p in card["points"]]
    assert min(xs) == pytest.approx(0.0) and max(xs) <= snap["stroke_in"] + 1e-6
    assert card["pprl_lb"] > card["mprl_lb"]
    assert card["pprl_lb"] >= card["buoyant_rod_weight_lb"] + 0.9 * card["fluid_load_lb"]
    assert card["polished_rod_hp"] > 0
    assert card["primary_diagnosis"] == "NORMAL"


def test_dynacard_flags_cold_fast_pumping():
    card = dc.dynacard(tp.twin_snapshot(cold_fast()), 18.0)
    codes = {d["code"] for d in card["diagnosis"]}
    assert "FLUID_POUND" in codes
    assert card["goodman_loading_percent"] > dc.dynacard(tp.twin_snapshot(state()), 18.0)["goodman_loading_percent"]
    # Colder tubing fluid -> more viscous drag on the rods.
    assert card["viscous_drag_lb"] > dc.dynacard(tp.twin_snapshot(state()), 18.0)["viscous_drag_lb"]


def test_rod_float_detected_for_very_viscous_fluid():
    snap = tp.twin_snapshot(state(steam_volume_t=0.0, steam_injection_pressure_bar=0.0,
                                  reservoir_temperature_c=20.0, api_gravity=12.0, spm=9.0))
    card = dc.dynacard(snap, 12.0)
    assert card["mprl_lb"] < 0.25 * card["buoyant_rod_weight_lb"]
    assert {"ROD_FLOAT", "ROD_FLOAT_MARGINAL"} & {d["code"] for d in card["diagnosis"]}


# ---------------- CSS cycle ----------------

def test_cycle_cutoff_maximises_average_rate():
    res = css_cycle.simulate_cycle(state())
    prod = [p for p in res["series"] if p["phase"] == "PRODUCTION"]
    down = res["injection_days"] + res["soak_days"]
    avgs = [p["cum_oil_bbl"] / (down + i + 1) for i, p in enumerate(prod)]
    best = int(np.argmax(avgs)) + 1
    assert res["optimal_cutoff_production_day"] == best
    assert prod[0]["oil_rate_bopd"] > prod[-1]["oil_rate_bopd"]  # declines as it cools
    assert res["incremental_oil_bbl"] > 0
    assert res["cycle_sor_cwe"] == pytest.approx(
        850.0 * css_cycle.BBL_CWE_PER_T / res["cycle_oil_bbl"], rel=1e-3)


def test_cycle_plan_picks_best_feasible():
    plan = css_cycle.plan_cycle(state())
    assert plan["candidates_evaluated"] == 25
    feasible = [c for c in plan["candidates"] if c["feasible"]]
    assert plan["recommended"]["feasible"]
    assert plan["recommended"]["average_cycle_rate_bopd"] == max(c["average_cycle_rate_bopd"] for c in feasible)


# ---------------- analytics ----------------

def _hist(k=0.3, n=20, D=0.03):
    out = []
    for i in range(n):
        twin = 100.0 * math.exp(-D * i)
        out.append({"timestamp": f"2026-07-{i + 1:02d}T00:00:00+00:00", "css_phase": "PRODUCTION",
                    "oil_rate_bopd": k * twin, "twin_oil_bopd": twin, "wellhead_pressure_bar": 10.0 + 0.01 * i,
                    "reservoir_pressure_bar": 30.0 + 0.01 * (i % 3), "spm": 5.0 + 0.01 * (i % 2)})
    return out


def test_calibration_recovers_scale_factor():
    c = analytics.calibrate(_hist(k=0.27))
    assert c["status"] == "CALIBRATED"
    assert c["k"] == pytest.approx(0.27, abs=1e-3)
    assert c["mape_percent"] < c["uncalibrated_mape_percent"]
    assert analytics.calibrate(_hist(n=2))["status"] == "INSUFFICIENT_DATA"


def test_calibration_is_robust_to_fault_periods():
    h = _hist(k=0.3, n=20)
    for i in (5, 6, 12):  # pump-wear readings at 40% of normal
        h[i] = dict(h[i], oil_rate_bopd=h[i]["oil_rate_bopd"] * 0.4)
    c = analytics.calibrate(h)
    assert c["outliers_excluded"] == 3
    assert c["k"] == pytest.approx(0.3, abs=1e-3)


def test_anomaly_detects_spike_and_divergence():
    h = _hist(n=20)
    h[-1] = dict(h[-1], wellhead_pressure_bar=25.0, oil_rate_bopd=h[-1]["oil_rate_bopd"] * 0.2)
    found = analytics.detect_anomalies(h, k=0.3)
    kinds = {(a["type"], a["metric"]) for a in found if a["timestamp"] == h[-1]["timestamp"]}
    assert ("STATISTICAL_OUTLIER", "wellhead_pressure_bar") in kinds
    assert ("TWIN_DIVERGENCE", "oil_rate_bopd") in kinds


def test_decline_forecast_fits_exponential():
    f = analytics.decline_forecast(_hist(D=0.03))
    assert f["status"] == "FITTED"
    assert f["decline_rate_per_day"] == pytest.approx(0.03, abs=1e-4)
    assert f["r2"] > 0.999
    rates = [p["oil_rate_bopd"] for p in f["forecast"]]
    assert all(a >= b for a, b in zip(rates, rates[1:]))


# ---------------- ML ----------------

def test_models_train_with_useful_holdout_metrics():
    info = ml_models.model_info()
    assert info["label_source"] == "SYNTHETIC_HAZARD_MODEL"
    for m in info["models"]:
        # Labels are Bernoulli draws, so even the true hazard cannot rank them perfectly:
        # the model must get close to that ceiling (oracle AUC), not to 1.0.
        assert m["metrics"]["auc"] > 0.7
        assert m["metrics"]["auc"] >= 0.9 * m["metrics"]["oracle_auc"]
        assert 0.0 < m["metrics"]["holdout_positive_rate"] < 0.3


def test_predictions_are_probabilities_and_directional():
    hot = ml_models.predict(state())
    bad = ml_models.predict(cold_fast())
    for name in ("rod_failure", "pump_unsetting"):
        for r in (hot, bad):
            assert 0.0 <= r["predictions"][name]["probability"] <= 1.0
            assert len(r["predictions"][name]["top_drivers"]) > 0
        assert bad["predictions"][name]["probability"] > hot["predictions"][name]["probability"]


def test_ml_is_deterministic():
    assert ml_models.predict(state()) == ml_models.predict(state())


# ---------------- live field ----------------

def test_field_simulator_is_reproducible_and_cycles():
    a, b = live_field.FieldSimulator(), live_field.FieldSimulator()
    ra = [a.step() for _ in range(40)]
    rb = [b.step() for _ in range(40)]
    assert ra == rb
    phases = {r["reading"]["css_phase"] for step in ra for r in step}
    assert {"INJECTION", "SOAK", "PRODUCTION"} <= phases
    for step in ra:
        for r in step:
            if r["reading"]["css_phase"] != "PRODUCTION":
                assert r["reading"]["oil_rate_bopd"] == 0.0


# ---------------- API ----------------

def test_simulate_accepts_vfd_override():
    client.post("/api/v1/telemetry/ingest", json=BASE)
    data = client.post("/api/v1/wells/BGW-01/simulate", json={"vfd_percent": 70.0}).json()
    assert data["scenario_inputs"]["spm"] == pytest.approx(7.0)
    assert data["scenario_inputs"]["vfd_setpoint_percent"] == pytest.approx(70.0)
    assert data["scenario"]["pump_capacity_bopd"] > data["current"]["pump_capacity_bopd"]


def test_optimize_reports_vfd_setpoints():
    client.post("/api/v1/telemetry/ingest", json=BASE)
    data = client.post("/api/v1/wells/BGW-01/optimize", json={}).json()
    rec = data["recommended"]["inputs"]
    assert rec["vfd_setpoint_percent"] == pytest.approx(tp.vfd_for_spm(rec["spm"]))
    assert all(s["inputs"]["vfd_setpoint_percent"] is not None for s in data["top_scenarios"])


def test_block4_endpoints_404_for_unknown_well():
    for path in ("cycle", "dynacard", "predict", "history", "analytics"):
        assert client.get(f"/api/v1/wells/NOPE/{path}").status_code == 404
    assert client.post("/api/v1/wells/NOPE/cycle/plan", json={}).status_code == 404


def test_cycle_dynacard_predict_endpoints():
    client.post("/api/v1/telemetry/ingest", json=BASE)
    cyc = client.get("/api/v1/wells/BGW-01/cycle").json()
    assert cyc["optimal_cutoff_production_day"] >= 1 and len(cyc["series"]) > 0
    plan = client.post("/api/v1/wells/BGW-01/cycle/plan",
                       json={"steam_grid_t": [600, 900], "soak_grid_h": [24, 72]}).json()
    assert plan["candidates_evaluated"] == 4
    card = client.get("/api/v1/wells/BGW-01/dynacard").json()
    assert card["primary_diagnosis"] and len(card["points"]) == dc.CARD_POINTS
    pred = client.get("/api/v1/wells/BGW-01/predict").json()
    assert set(pred["predictions"]) == {"rod_failure", "pump_unsetting"}
    assert client.get("/api/v1/ml/model").json()["models"]


def test_seed_history_analytics_and_calibration():
    seed = client.post("/api/v1/demo/seed", json={"days": 40}).json()
    assert seed["status"] == "SEEDED" and len(seed["wells"]) == 4
    wells = client.get("/api/v1/wells").json()
    assert wells["total_wells"] == 4
    hist = client.get("/api/v1/wells/BGW-01/history").json()
    assert hist["count"] == seed["ticks"]
    an = client.get("/api/v1/wells/BGW-01/analytics").json()
    # Auto-calibration discovers the simulator's hidden productivity factor.
    assert an["calibration"]["status"] == "CALIBRATED"
    assert an["calibration"]["k"] == pytest.approx(live_field.PROFILES[0]["k_true"], abs=0.03)
    overview = client.get("/api/v1/field/overview").json()
    assert overview["total_wells"] == 4
    assert overview["field_oil_rate_bopd"] >= 0.0


def test_alerts_raise_and_acknowledge():
    client.post("/api/v1/telemetry/ingest", json=dict(
        BASE, steam_volume_t=0.0, steam_injection_pressure_bar=0.0, spm=9.0, stroke_in=140.0))
    alerts = client.get("/api/v1/alerts").json()
    assert alerts["total"] >= 1
    first = alerts["alerts"][0]
    assert first["severity"] in ("HIGH", "MODERATE")
    acked = client.post(f"/api/v1/alerts/{first['alert_id']}/ack").json()
    assert acked["acknowledged"] is True
    assert client.post("/api/v1/alerts/ALR-99999/ack").status_code == 404
    # Persistent condition does not duplicate on the next identical reading.
    before = client.get("/api/v1/alerts").json()["total"]
    client.post("/api/v1/telemetry/ingest", json=dict(
        BASE, timestamp="2026-09-29T11:00:00+00:00", steam_volume_t=0.0,
        steam_injection_pressure_bar=0.0, spm=9.0, stroke_in=140.0))
    after = client.get("/api/v1/alerts").json()["total"]
    assert after == before


def test_live_tick_and_status():
    assert client.get("/api/v1/live/status").json()["running"] is False
    r = client.post("/api/v1/live/tick").json()
    assert len(r["readings"]) == 4 and r["live"]["ticks"] == 1
    client.post("/api/v1/live/tick")
    assert client.get("/api/v1/live/status").json()["ticks"] == 2
    assert client.post("/api/v1/live/stop").json()["running"] is False


def test_stream_sends_hello_event():
    client.post("/api/v1/telemetry/ingest", json=BASE)
    with client.stream("GET", "/api/v1/stream?max_events=1") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = "".join(resp.iter_text())
    assert body.startswith("event: hello")
    payload = json.loads(body.split("data: ", 1)[1].strip())
    assert payload["wells"] == ["BGW-01"]


def test_ingest_contract_unchanged():
    resp = client.post("/api/v1/telemetry/ingest", json=BASE)
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "TELEMETRY_ACCEPTED"
    assert "risk_score" not in body and "confidence" not in body
    assert body["well_state"]["days_in_phase"] == 0.0
