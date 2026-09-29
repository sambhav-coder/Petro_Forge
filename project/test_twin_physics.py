"""Deterministic unit + endpoint tests for the Block 2 engineering foundation.

Part 14 checklist: monotonicity/qualitative behavior is asserted rather
than arbitrary exact numbers, except where constants make values exact.
"""

import math
import os
import importlib.util
import pytest
from fastapi.testclient import TestClient

import twin_physics as tp

app_path = os.path.join(os.path.dirname(__file__), "app.py")
spec = importlib.util.spec_from_file_location("app_sih26120_block2", app_path)
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


def twin_state(**overrides):
    """Lightweight WellTelemetry-like object for direct snapshot tests."""
    from types import SimpleNamespace

    data = make_payload(**overrides)
    data["css_phase"] = SimpleNamespace(value=data["css_phase"])
    return SimpleNamespace(**data)


# ---- 1-3: temperature response ----

def test_temperature_increases_with_heating():
    cold = tp.heating_temperature(47.0, 0.8, 12.0)
    hot = tp.heating_temperature(47.0, 0.8, 48.0)
    assert hot > cold > 47.0
    # Stronger steam intensity -> hotter, all else equal.
    assert tp.heating_temperature(47.0, 1.0, 48.0) > tp.heating_temperature(47.0, 0.2, 48.0)
    # Snapshot level: more steam volume -> higher estimated temperature.
    t_lo = tp.twin_snapshot(twin_state(steam_volume_t=100.0))["estimated_temperature_c"]
    t_hi = tp.twin_snapshot(twin_state(steam_volume_t=900.0))["estimated_temperature_c"]
    assert t_hi > t_lo


def test_temperature_is_bounded():
    t = tp.heating_temperature(47.0, 1.0, 100000.0)
    assert t <= 47.0 + tp.DT_MAX_C + 1e-9
    assert tp.heating_temperature(47.0, 5.0, 48.0) <= 47.0 + tp.DT_MAX_C + 1e-9
    assert tp.heating_temperature(47.0, 0.0, 48.0) == pytest.approx(47.0)


def test_cooling_behavior_sensible():
    cooled = tp.cooling_temperature(150.0, 47.0, 48.0)
    assert 47.0 < cooled < 150.0
    assert tp.cooling_temperature(150.0, 47.0, 24.0) > tp.cooling_temperature(150.0, 47.0, 240.0)
    # IDLE snapshot must be cooler than the same well left in SOAK.
    idle = tp.twin_snapshot(twin_state(css_phase="IDLE"))["estimated_temperature_c"]
    soak = tp.twin_snapshot(twin_state(css_phase="SOAK"))["estimated_temperature_c"]
    assert idle < soak


# ---- 4-5: viscosity ----

def test_viscosity_decreases_with_temperature():
    assert tp.viscosity_cp(150.0) < tp.viscosity_cp(47.0) < tp.viscosity_cp(20.0)


def test_viscosity_always_positive_and_finite():
    for t in (0.0, 47.0, 120.0, 350.0):
        mu = tp.viscosity_cp(t)
        assert math.isfinite(mu) and mu > 0.0


# ---- 6: mobility ----

def test_mobility_decreases_with_viscosity():
    assert tp.mobility_factor(50.0) > tp.mobility_factor(350.0) > tp.mobility_factor(5000.0)
    assert tp.mobility_factor(350.0) == pytest.approx(1.0)
    assert tp.mobility_factor(0.0) >= 0.0


# ---- 7-9: inflow ----

def test_inflow_increases_with_drawdown():
    q_lo = tp.reservoir_inflow_bopd(20.0, 15.0, 350.0)
    q_hi = tp.reservoir_inflow_bopd(40.0, 15.0, 350.0)
    assert q_hi > q_lo >= 0.0


def test_inflow_decreases_with_viscosity():
    assert tp.reservoir_inflow_bopd(28.5, 12.0, 100.0) > tp.reservoir_inflow_bopd(28.5, 12.0, 5000.0)


def test_inflow_never_negative():
    assert tp.reservoir_inflow_bopd(10.0, 12.0, 350.0) == 0.0
    assert tp.reservoir_inflow_bopd(12.0, 12.0, 350.0) == 0.0
    assert tp.reservoir_inflow_bopd(0.0, 0.0, 350.0) == 0.0


# ---- 10-12: pump capacity ----

def test_pump_capacity_increases_with_spm():
    assert tp.theoretical_pump_capacity_bopd(8.0, 96.0) > tp.theoretical_pump_capacity_bopd(4.0, 96.0)


def test_pump_capacity_increases_with_stroke():
    assert tp.theoretical_pump_capacity_bopd(5.0, 120.0) > tp.theoretical_pump_capacity_bopd(5.0, 60.0)


def test_fillage_efficiency_bounds():
    q = tp.theoretical_pump_capacity_bopd(5.0, 96.0)
    assert tp.actual_pump_capacity_bopd(q, 1.0, 1.0) == pytest.approx(q)
    assert tp.actual_pump_capacity_bopd(q, 0.0, 0.75) == 0.0
    # Out-of-range inputs are clamped, never negative or amplifying.
    assert tp.actual_pump_capacity_bopd(q, 2.0, 1.5) == pytest.approx(q)
    assert tp.actual_pump_capacity_bopd(q, -0.5, 0.75) == 0.0
    assert tp.actual_pump_capacity_bopd(0.0, 0.85, 0.75) == 0.0


# ---- 13: coupling ----

def test_production_is_min_of_inflow_and_pump():
    prod, limiting = tp.couple_production_bopd(10.0, 30.0)
    assert prod == pytest.approx(10.0) and limiting == "INFLOW_LIMITED"
    prod, limiting = tp.couple_production_bopd(40.0, 25.0)
    assert prod == pytest.approx(25.0) and limiting == "PUMP_LIMITED"


# ---- 14: SOR ----

def test_sor_handles_zero_oil_safely():
    value, status_ = tp.steam_oil_ratio(850.0, 0.0)
    assert value is None and status_ == "UNDEFINED_ZERO_OIL"
    value, status_ = tp.steam_oil_ratio(850.0, 1000.0)
    assert value == pytest.approx(0.85) and status_ == "DEFINED"


# ---- 15: energy ----

def test_energy_non_negative():
    e = tp.energy_estimate_kwh(850.0, 5.0, 96.0, 20.0)
    assert e["steam_energy_kwh"] >= 0.0
    assert e["pumping_energy_kwh"] >= 0.0
    assert e["total_energy_kwh"] >= 0.0
    assert e["energy_per_barrel_kwh"] is not None and e["energy_per_barrel_kwh"] >= 0.0
    e0 = tp.energy_estimate_kwh(0.0, 0.0, 0.0, 0.0)
    assert e0["total_energy_kwh"] == 0.0
    assert e0["energy_per_barrel_kwh"] is None


# ---- 16-17: risk + snapshot determinism ----

def test_risks_deterministic_with_valid_levels():
    snap1 = tp.twin_snapshot(twin_state())
    snap2 = tp.twin_snapshot(twin_state())
    assert snap1 == snap2
    for key in ("rod_float_risk", "impact_risk", "pump_unsetting_risk"):
        r = snap1[key]
        assert r["risk_level"] in ("LOW", "MODERATE", "HIGH")
        assert 0.0 <= r["risk_score"] <= 1.0
        assert isinstance(r["reason"], str) and len(r["reason"]) > 0
    assert snap1["overall_engineering_status"] in ("NOMINAL", "ELEVATED", "HIGH_RISK")


def test_snapshot_has_no_nan_or_infinity():
    snap = tp.twin_snapshot(twin_state())
    numeric = [
        snap["estimated_temperature_c"], snap["estimated_viscosity_cp"],
        snap["mobility_factor"], snap["estimated_reservoir_inflow_bopd"],
        snap["pump_capacity_bopd"], snap["estimated_oil_production_bopd"],
        snap["steam_energy_kwh"], snap["pumping_energy_kwh"], snap["total_energy_kwh"],
    ]
    assert all(math.isfinite(v) for v in numeric)
    # The pump lifts total liquid; oil is the non-water share of it (Block 4).
    assert snap["estimated_liquid_production_bpd"] == pytest.approx(
        min(snap["estimated_reservoir_inflow_bopd"], snap["pump_capacity_bopd"])
    )
    assert snap["estimated_oil_production_bopd"] == pytest.approx(
        snap["estimated_liquid_production_bpd"] * (1 - snap["water_cut_percent"] / 100.0), abs=1e-3
    )
    dry = tp.twin_snapshot(twin_state(water_cut_percent=0.0))
    assert dry["estimated_oil_production_bopd"] == pytest.approx(
        min(dry["estimated_reservoir_inflow_bopd"], dry["pump_capacity_bopd"])
    )


def test_snapshot_explanations_reference_calculations():
    snap = tp.twin_snapshot(twin_state())
    assert "Steam heating" in snap["explanations"]["temperature"]
    assert "viscosity" in snap["explanations"]["production"].lower() or "inflow" in snap["explanations"]["production"].lower()
    assert f"{snap['estimated_oil_production_bopd']:.1f}" in snap["explanations"]["production"]


# ---- 18-19: twin API endpoint ----

def test_twin_endpoint_returns_calculated_snapshot():
    client.post("/api/v1/telemetry/ingest", json=make_payload())
    response = client.get("/api/v1/wells/BGW-01/twin")
    assert response.status_code == 200
    data = response.json()
    assert data["well_id"] == "BGW-01"
    # Steam was injected: estimated temperature must exceed the baseline.
    assert data["estimated_temperature_c"] > data["baseline_reservoir_temperature_c"]
    assert data["estimated_viscosity_cp"] > 0.0
    assert data["estimated_oil_production_bopd"] <= data["estimated_reservoir_inflow_bopd"] + 1e-9
    assert data["estimated_oil_production_bopd"] <= data["pump_capacity_bopd"] + 1e-9
    assert data["overall_engineering_status"] in ("NOMINAL", "ELEVATED", "HIGH_RISK")
    assert "prototype" in data["prototype_disclaimer"].lower()


def test_twin_endpoint_unknown_well_404():
    response = client.get("/api/v1/wells/BGW-NOPE/twin")
    assert response.status_code == 404


def test_ingest_carries_concise_twin_summary():
    response = client.post("/api/v1/telemetry/ingest", json=make_payload())
    assert response.status_code == 201
    summary = response.json()["twin_summary"]
    assert summary["overall_engineering_status"] in ("NOMINAL", "ELEVATED", "HIGH_RISK")
    assert summary["estimated_oil_production_bopd"] >= 0.0
    assert isinstance(summary["top_reason"], str)
    # Block 1 contract intact: accepted state echo + no fake AI fields.
    assert response.json()["status"] == "TELEMETRY_ACCEPTED"
    assert "risk_score" not in response.json()
    assert "confidence" not in response.json()
