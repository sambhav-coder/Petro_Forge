"""P5 SRP pump performance tests: dynacard compat, horsepower, capacity,
efficiency states, structured diagnostics, recommendations, ML evidence,
API compatibility."""

import importlib.util
import math
import os

import pytest
from fastapi.testclient import TestClient

import srp_dynacard as dc
import srp_performance as perf
import twin_physics as tp

app_path = os.path.join(os.path.dirname(__file__), "app.py")
spec = importlib.util.spec_from_file_location("app_sih26120_srp", app_path)
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


def _snap_card(**over):
    client.post("/api/v1/telemetry/ingest", json=_payload(**over))
    rec = app_module.WELL_STORE["BGW-01"]
    snap = tp.twin_snapshot(rec)
    return snap, dc.dynacard(snap, rec.api_gravity)


# 1-4. Existing dynacard behavior preserved.
def test_1_dynacard_keys_intact():
    snap, card = _snap_card()
    for f in ("pprl_lb", "mprl_lb", "goodman_loading_percent",
              "estimated_pump_fillage", "polished_rod_hp", "diagnosis",
              "primary_diagnosis", "points"):
        assert f in card


def test_2_pprl_mprl_ordering():
    _, card = _snap_card()
    assert card["pprl_lb"] >= card["mprl_lb"]
    assert card["pprl_lb"] > 0


def test_3_goodman_range():
    _, card = _snap_card()
    assert 0.0 <= card["goodman_loading_percent"] <= 300.0


def test_4_fillage_clamped():
    _, card = _snap_card()
    assert 0.0 <= card["estimated_pump_fillage"] <= 1.0


# 5-7. Horsepower: shoelace recompute, units, zero inputs.
def test_5_horsepower_matches_card_area():
    _, card = _snap_card()
    pts = [(p["position_in"], p["load_lb"]) for p in card["points"]]
    area = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        area += x1 * y2 - x2 * y1
    area = abs(area) / 2.0
    assert card["polished_rod_hp"] == \
        pytest.approx(area * card["spm"] / (12.0 * 33000.0), rel=1e-3)


def test_6_horsepower_kw_conversion():
    snap, card = _snap_card()
    summary = perf.performance_summary(snap, card)
    assert summary["power"]["polished_rod_kw"] == \
        pytest.approx(card["polished_rod_hp"] * 0.7457, rel=1e-3)
    assert summary["power"]["unit"] == "hp"


def test_7_zero_spm_zero_power():
    snap, card = _snap_card(spm=0.0)
    assert card["polished_rod_hp"] == 0.0
    eff = perf.pump_efficiency(snap["estimated_liquid_production_bpd"],
                               tp.theoretical_pump_capacity_bopd(0.0, 96.0))
    assert eff["status"] == "UNAVAILABLE"


# 8. Theoretical capacity geometry.
def test_8_capacity_geometry():
    cap = perf.pump_capacity_breakdown(6.0, 96.0)
    expected = (math.pi / 4.0) * 2.0 ** 2 * 96.0 * 6.0 * 1440.0 / 9702.0
    assert cap["theoretical_capacity_bopd"] == pytest.approx(expected, abs=1e-3)
    assert cap["bore_diameter_in"] == 2.0
    assert "NOT a field-verified" in cap["geometry_note"]


# 9-12. Efficiency states.
def test_9_efficiency_normal():
    snap, _ = _snap_card()
    eff = perf.pump_efficiency(snap["estimated_liquid_production_bpd"],
                               snap["pump_theoretical_capacity_bopd"])
    assert eff["status"] == "CALCULATED"
    assert 0.0 <= eff["value"] <= 1.0 + 1e-9


def test_10_zero_theoretical_unavailable():
    eff = perf.pump_efficiency(100.0, 0.0)
    assert eff["status"] == "UNAVAILABLE"
    assert eff["value"] is None


def test_11_missing_production_unavailable():
    eff = perf.pump_efficiency(None, 250.0)
    assert eff["status"] == "UNAVAILABLE"


def test_12_negative_invalid():
    assert perf.pump_efficiency(-5.0, 250.0)["status"] == "INVALID"
    assert perf.pump_efficiency(50.0, -1.0)["status"] == "INVALID"


# 13-16. Diagnosis triggers.
def test_13_rod_float_diagnosis():
    # Cold, thick fluid at high SPM drives downstroke drag past buoyant weight.
    snap, card = _snap_card(reservoir_temperature_c=46.0, steam_volume_t=0.0,
                            steam_injection_pressure_bar=0.0, spm=12.0)
    codes = {d["code"] for d in card["diagnosis"]}
    assert codes & {"ROD_FLOAT", "ROD_FLOAT_MARGINAL"}
    eff = perf.pump_efficiency(snap["estimated_liquid_production_bpd"],
                               snap["pump_theoretical_capacity_bopd"])
    diags = perf.diagnose_loading(card, snap, eff)
    assert any(d["code"] in ("ROD_FLOAT", "ROD_FLOAT_MARGINAL") for d in diags)


def test_14_fluid_pound_diagnosis():
    # Pump outrunning inflow -> fillage below threshold.
    snap, card = _snap_card(oil_rate_bopd=5.0, spm=12.0, stroke_in=144.0)
    eff = perf.pump_efficiency(snap["estimated_liquid_production_bpd"],
                               snap["pump_theoretical_capacity_bopd"])
    diags = perf.diagnose_loading(card, snap, eff)
    assert any(d["code"] == "POSSIBLE_FLUID_POUND" for d in diags)


def test_15_rod_loading_diagnosis_present_in_codes():
    _, card = _snap_card()
    assert isinstance(card["goodman_loading_percent"], float)
    # Structured layer maps overload codes when the card raises them.
    hot = dict(card, diagnosis=[{"code": "ROD_OVERLOAD", "severity": "HIGH",
                                 "detail": "x"}],
               goodman_loading_percent=112.0)
    snap, _ = _snap_card()
    eff = perf.pump_efficiency(100.0, 250.0)
    diags = perf.diagnose_loading(hot, snap, eff)
    assert any(d["code"] == "SUSPECTED_ROD_OVERLOAD" for d in diags)


def test_16_viscous_drag_diagnosis():
    snap, card = _snap_card()
    forged = dict(card, viscous_drag_lb=card["buoyant_rod_weight_lb"] * 0.8,
                  diagnosis=[{"code": "NORMAL", "severity": "LOW", "detail": "x"}])
    eff = perf.pump_efficiency(100.0, 250.0)
    diags = perf.diagnose_loading(forged, snap, eff)
    assert any(d["code"] == "EXCESSIVE_VISCOUS_DRAG" for d in diags)


# 17-18. Evidence + tied recommendations.
def test_17_diagnostic_evidence_nonempty():
    snap, card = _snap_card()
    eff = perf.pump_efficiency(snap["estimated_liquid_production_bpd"],
                               snap["pump_theoretical_capacity_bopd"])
    for d in perf.diagnose_loading(card, snap, eff):
        assert d["evidence"], d["code"]
        assert "failure" not in " ".join(d["evidence"]).lower() or \
            "confirmed" not in " ".join(d["evidence"]).lower()
        assert "not a confirmed field failure" in d["wording"]


def test_18_recommendations_tied_to_flagged_codes():
    snap, card = _snap_card()
    eff = perf.pump_efficiency(snap["estimated_liquid_production_bpd"],
                               snap["pump_theoretical_capacity_bopd"])
    diags = perf.diagnose_loading(card, snap, eff)
    recs = perf.operating_recommendations(diags)
    flagged = {d["code"] for d in diags if d["code"] != "NORMAL_OPERATION"}
    assert {r["for_diagnosis"] for r in recs} >= flagged
    assert all(r["action"] for r in recs)


# 19-20. Synthetic provenance + insufficient-data behavior.
def test_19_ml_evidence_keeps_synthetic_provenance():
    snap, card = _snap_card()
    ml_health = {"mode": "SYNTHETIC", "production_safe": False,
                 "health_status": "AT_RISK"}
    summary = perf.performance_summary(snap, card, ml_health)
    assert summary["ml_health"]["status"] == "ATTACHED_SEPARATE_EVIDENCE"
    assert summary["ml_health"]["mode"] == "SYNTHETIC"
    assert summary["ml_health"]["production_safe"] is False


def test_20_insufficient_ml_data_explicit():
    snap, card = _snap_card()
    summary = perf.performance_summary(snap, card, None)
    assert summary["ml_health"]["status"] == "INSUFFICIENT_DATA"


# 21. Existing SRP API compatibility (old keys + new block).
def test_21_dynacard_api_compat():
    _snap_card()
    body = client.get("/api/v1/wells/BGW-01/dynacard").json()
    for f in ("pprl_lb", "mprl_lb", "goodman_loading_percent",
              "estimated_pump_fillage", "polished_rod_hp", "diagnosis",
              "primary_diagnosis", "points"):
        assert f in body
    pp = body["pump_performance"]
    assert pp["power"]["polished_rod_hp"] == body["polished_rod_hp"]
    assert pp["efficiency"]["status"] in ("CALCULATED", "UNAVAILABLE", "INVALID")
    assert pp["mode"] == "PROTOTYPE_PHYSICS"
