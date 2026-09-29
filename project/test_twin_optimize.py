"""Tests for Block 3: what-if simulation + joint CSSxSRP optimization."""

import copy
import os
import importlib.util
import time
import pytest
from fastapi.testclient import TestClient

import twin_optimize as to
import twin_physics as tp

app_path = os.path.join(os.path.dirname(__file__), "app.py")
spec = importlib.util.spec_from_file_location("app_sih26120_block3", app_path)
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)
app = app_module.app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_state():
    app_module.reset_block1_state()
    yield
    app_module.reset_block1_state()


def make_payload(well_id="BGW-01", **overrides):
    payload = {
        "well_id": well_id,
        "timestamp": "2026-09-29T10:00:00+00:00",
        "reservoir_temperature_c": 47.0,
        "reservoir_pressure_bar": 28.5,
        "api_gravity": 18.0,
        "wellhead_pressure_bar": 12.0,
        "oil_rate_bopd": 22.5,
        "steam_volume_t": 850.0,
        "steam_injection_pressure_bar": 65.0,
        "soak_time_h": 48.0,
        "css_phase": "PRODUCTION",
        "spm": 5.0,
        "stroke_in": 96.0,
        "vfd_percent": 55.0,
        "water_cut_percent": 35.0,
    }
    payload.update(overrides)
    return payload


def ingest(well_id="BGW-01", **overrides):
    response = client.post("/api/v1/telemetry/ingest", json=make_payload(well_id, **overrides))
    assert response.status_code == 201
    return response.json()


def scenario(**overrides):
    base = {"steam_volume_t": 1000.0, "soak_time_h": 72.0, "spm": 6.0}
    base.update(overrides)
    return base


# ---- 1-5: simulate endpoint ----

def test_simulate_endpoint_works():
    ingest()
    response = client.post("/api/v1/wells/BGW-01/simulate", json=scenario())
    assert response.status_code == 200
    data = response.json()
    assert data["well_id"] == "BGW-01"
    assert data["scenario_inputs"]["steam_volume_t"] == 1000.0
    assert data["scenario"]["estimated_oil_production_bopd"] >= 0.0
    assert data["scenario"]["sor_status"] in ("DEFINED", "UNDEFINED_ZERO_OIL")
    assert data["current"]["estimated_oil_production_bopd"] >= 0.0
    assert "production_delta_bopd" in data["delta"]
    assert data["mode"] == "PROTOTYPE_SIMULATION"


def test_simulate_does_not_mutate_store():
    ingest()
    before_well = client.get("/api/v1/wells/BGW-01").json()
    before_twin = client.get("/api/v1/wells/BGW-01/twin").json()
    before_audit = client.get("/api/v1/audit/logs").json()["total_records"]
    client.post("/api/v1/wells/BGW-01/simulate", json=scenario(steam_volume_t=5000.0, spm=12.0))
    assert client.get("/api/v1/wells/BGW-01").json() == before_well
    assert client.get("/api/v1/wells/BGW-01/twin").json() == before_twin
    assert client.get("/api/v1/audit/logs").json()["total_records"] == before_audit
    assert client.get("/api/v1/wells").json()["total_wells"] == 1


def test_same_scenario_same_output():
    ingest()
    first = client.post("/api/v1/wells/BGW-01/simulate", json=scenario()).json()
    second = client.post("/api/v1/wells/BGW-01/simulate", json=scenario()).json()
    assert first == second


def test_simulate_unknown_well_404():
    assert client.post("/api/v1/wells/BGW-NOPE/simulate", json=scenario()).status_code == 404
    assert client.post("/api/v1/wells/BGW-NOPE/optimize", json={}).status_code == 404


def test_invalid_scenario_returns_422():
    ingest()
    assert client.post(
        "/api/v1/wells/BGW-01/simulate", json={"steam_volume_t": -5.0}
    ).status_code == 422
    assert client.post(
        "/api/v1/wells/BGW-01/simulate", json={"spm": 99.0}
    ).status_code == 422


# ---- 6-12: optimizer endpoint ----

def test_optimizer_returns_recommendation():
    ingest()
    response = client.post("/api/v1/wells/BGW-01/optimize", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["well_id"] == "BGW-01"
    assert data["scenarios_evaluated"] == 243
    assert isinstance(data["objective_score"], float)
    assert data["recommended"]["estimated_oil_production_bopd"] >= 0.0
    assert len(data["top_scenarios"]) == 5
    assert len(data["why_recommended"]) >= 3
    assert len(data["assumptions"]) >= 3


def test_optimizer_output_respects_bounds():
    ingest()
    data = client.post("/api/v1/wells/BGW-01/optimize", json={}).json()
    for item in data["top_scenarios"]:
        for key, (lo, hi) in to.BOUNDS.items():
            assert lo <= item["inputs"][key] <= hi
    for key, (lo, hi) in to.BOUNDS.items():
        assert lo <= data["recommended"]["inputs"][key] <= hi


def test_top_scenarios_sorted_by_score():
    ingest()
    data = client.post("/api/v1/wells/BGW-01/optimize", json={}).json()
    scores = [s["score"] for s in data["top_scenarios"]]
    assert scores == sorted(scores, reverse=True)
    assert data["objective_score"] == pytest.approx(scores[0])
    assert [s["rank"] for s in data["top_scenarios"]] == [1, 2, 3, 4, 5]


def test_repeated_optimization_identical():
    ingest()
    first = client.post("/api/v1/wells/BGW-01/optimize", json={}).json()
    second = client.post("/api/v1/wells/BGW-01/optimize", json={}).json()
    assert first == second


def test_recommendation_reasons_reference_values():
    ingest()
    data = client.post("/api/v1/wells/BGW-01/optimize", json={}).json()
    assert all(isinstance(r, str) and len(r) > 0 for r in data["why_recommended"])
    # Every reason must reference at least one calculated number.
    assert all(any(ch.isdigit() for ch in r) for r in data["why_recommended"])


def test_reasons_track_actual_directions():
    ingest()
    twin = client.get("/api/v1/wells/BGW-01/twin").json()
    cur = copy.deepcopy(twin)
    rec = copy.deepcopy(twin)
    rec["estimated_temperature_c"] = cur["estimated_temperature_c"] + 20.0
    rec["estimated_viscosity_cp"] = cur["estimated_viscosity_cp"] / 2.0
    rec["mobility_factor"] = cur["mobility_factor"] * 2.0
    rec["steam_oil_ratio_t_per_bbl"] = (cur["steam_oil_ratio_t_per_bbl"] or 1.0) / 2.0
    reasons = to.build_reasons(cur, rec)
    joined = " ".join(reasons)
    assert "reduced estimated viscosity" in joined
    assert "increased the mobility factor" in joined
    assert "reduced SOR" in joined


def test_delta_mathematically_correct():
    ingest()
    data = client.post("/api/v1/wells/BGW-01/optimize", json={}).json()
    delta = data["delta"]
    assert delta["production_delta_bopd"] == pytest.approx(
        data["recommended"]["estimated_oil_production_bopd"]
        - data["current"]["estimated_oil_production_bopd"]
    )
    assert delta["energy_delta_kwh"] == pytest.approx(
        data["recommended"]["total_energy_kwh"] - data["current"]["total_energy_kwh"]
    )
    if data["recommended"]["steam_oil_ratio_t_per_bbl"] is not None and data["current"]["steam_oil_ratio_t_per_bbl"] is not None:
        assert delta["sor_delta_t_per_bbl"] == pytest.approx(
            data["recommended"]["steam_oil_ratio_t_per_bbl"]
            - data["current"]["steam_oil_ratio_t_per_bbl"]
        )


def test_optimizer_calls_physics_layer(monkeypatch):
    calls = []
    real_snapshot = tp.twin_snapshot

    def counting(state):
        calls.append(state.well_id)
        return real_snapshot(state)

    monkeypatch.setattr(tp, "twin_snapshot", counting)
    ingest()
    calls.clear()  # ingest also snapshots (twin_summary); isolate the optimize call
    data = client.post("/api/v1/wells/BGW-01/optimize", json={}).json()
    # 243 grid candidates + 1 current-state snapshot, all through twin_snapshot.
    assert len(calls) == data["scenarios_evaluated"] + 1
    assert set(calls) == {"BGW-01"}


# ---- 13-15: edges, custom grid, performance ----

def test_zero_edge_well_does_not_crash():
    ingest("BGW-ZERO", steam_volume_t=0.0, steam_injection_pressure_bar=0.0,
           soak_time_h=0.0, spm=0.0, stroke_in=0.0, reservoir_pressure_bar=10.0,
           wellhead_pressure_bar=12.0)
    sim = client.post("/api/v1/wells/BGW-ZERO/simulate", json={"spm": 6.0}).json()
    assert sim["scenario"]["estimated_oil_production_bopd"] >= 0.0
    opt = client.post("/api/v1/wells/BGW-ZERO/optimize", json={}).json()
    assert opt["scenarios_evaluated"] == 243
    assert opt["recommended"]["estimated_oil_production_bopd"] >= 0.0


def test_custom_grid_and_invalid_grid():
    ingest()
    small = {
        "search_grid": {
            "steam_volume_t": [600.0, 800.0],
            "steam_injection_pressure_bar": [65.0],
            "soak_time_h": [48.0],
            "spm": [5.0],
            "stroke_in": [96.0],
        }
    }
    data = client.post("/api/v1/wells/BGW-01/optimize", json=small).json()
    assert data["scenarios_evaluated"] == 2
    bad = copy.deepcopy(small)
    bad["search_grid"]["spm"] = [99.0]
    assert client.post("/api/v1/wells/BGW-01/optimize", json=bad).status_code == 422


def test_optimization_completes_quickly():
    ingest()
    started = time.perf_counter()
    response = client.post("/api/v1/wells/BGW-01/optimize", json={})
    elapsed = time.perf_counter() - started
    assert response.status_code == 200
    assert elapsed < 5.0
