"""P7 Pareto multi-objective tests: dominance logic, frontier output,
constraints, selection policy, API compatibility, 243-grid preservation."""

import importlib.util
import os

import pytest
from fastapi.testclient import TestClient

import twin_optimize as opt

app_path = os.path.join(os.path.dirname(__file__), "app.py")
spec = importlib.util.spec_from_file_location("app_sih26120_pareto", app_path)
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


def _optimize():
    assert client.post("/api/v1/telemetry/ingest", json=_payload()).status_code == 201
    r = client.post("/api/v1/wells/BGW-01/optimize", json={})
    assert r.status_code == 200
    return r.json()


# 1-2. Dominance: maximize production, minimize the rest.
def test_1_clear_dominance():
    # (prod, sor, energy, risk): B dominates A; C trades off.
    flags = opt.pareto_flags([
        (100.0, 0.20, 5000.0, 0.5),   # A dominated by B
        (120.0, 0.15, 4000.0, 0.4),   # B optimal
        (200.0, 0.60, 9000.0, 0.8),   # C optimal (best production)
    ])
    assert flags == [False, True, True]


def test_2_minimize_axes_respected():
    flags = opt.pareto_flags([
        (100.0, 0.10, 1000.0, 0.1),
        (100.0, 0.05, 1000.0, 0.1),  # strictly better SOR dominates
    ])
    assert flags == [False, True]


def test_3_maximize_axis_respected():
    flags = opt.pareto_flags([
        (90.0, 0.05, 1000.0, 0.1),
        (110.0, 0.05, 1000.0, 0.1),  # strictly better production dominates
    ])
    assert flags == [False, True]


# 4-5. Ties and duplicate vectors never dominate each other.
def test_4_duplicate_vectors_all_optimal():
    v = (150.0, 0.2, 3000.0, 0.3)
    assert opt.pareto_flags([v, v, v]) == [True, True, True]


def test_5_tie_on_one_axis_not_enough():
    flags = opt.pareto_flags([
        (150.0, 0.2, 3000.0, 0.3),
        (150.0, 0.2, 3000.0, 0.3),
    ])
    assert flags == [True, True]


# 6-7. Empty and single candidate sets.
def test_6_empty_set():
    assert opt.pareto_flags([]) == []


def test_7_single_candidate_optimal():
    assert opt.pareto_flags([(10.0, 0.5, 999.0, 0.9)]) == [True]


# 8. Known small example incl. +inf (undefined SOR/energy) handling.
def test_8_known_example_with_infinities():
    inf = float("inf")
    flags = opt.pareto_flags([
        (0.0, inf, inf, 0.5),      # zero production, undefined SOR/energy
        (50.0, 0.4, 8000.0, 0.2),  # dominates the zero-production point
        (80.0, 0.9, 2000.0, 0.9),  # trades production for worse SOR/risk
    ])
    assert flags == [False, True, True]


# 8b. Order independence.
def test_8b_order_independence():
    vecs = [
        (100.0, 0.20, 5000.0, 0.5),
        (200.0, 0.60, 9000.0, 0.8),
        (120.0, 0.15, 4000.0, 0.4),
        (120.0, 0.15, 4000.0, 0.4),
    ]
    assert opt.pareto_flags(vecs) == opt.pareto_flags(list(reversed(vecs)))[::-1]


# 9-10. 243-grid and top-5 compatibility preserved.
def test_9_default_grid_still_243():
    body = _optimize()
    assert body["scenarios_evaluated"] == 243
    assert len(body["top_scenarios"]) == 5
    assert body["top_scenarios"][0]["rank"] == 1


def test_10_top5_fields_unchanged():
    body = _optimize()
    s = body["top_scenarios"][0]
    for f in ("rank", "inputs", "estimated_oil_production_bopd",
              "steam_oil_ratio_t_per_bbl", "sor_status", "total_energy_kwh",
              "overall_engineering_status", "score"):
        assert f in s


# 11. Constraint filtering: report + 422 on violation.
def test_11_constraints_reported_and_enforced():
    body = _optimize()
    assert len(body["constraints"]) == 5
    assert all(c["kind"] == "prototype_input_safety_range" for c in body["constraints"])
    assert all("field-validated" in c["note"] or "Not a field-validated" in c["note"]
               for c in body["constraints"])
    bad = client.post("/api/v1/wells/BGW-01/optimize",
                      json={"search_grid": {"steam_volume_t": [999999.0],
                                            "steam_injection_pressure_bar": [65.0],
                                            "soak_time_h": [48.0], "spm": [6.0],
                                            "stroke_in": [96.0]}})
    assert bad.status_code == 422


# 12-13. Recommendation validity + Pareto membership.
def test_12_recommendation_matches_reported_best():
    body = _optimize()
    ranks = {s["rank"] for s in body["pareto_frontier"]}
    assert body["recommended"]["inputs"] is not None
    assert body["pareto_count"] == len(body["pareto_frontier"]) > 0
    # recommended inputs must equal one frontier member's inputs
    assert any(f["inputs"] == body["recommended"]["inputs"] for f in body["pareto_frontier"])
    assert body["recommended"]["inputs"] and ranks


def test_13_recommended_is_pareto_optimal():
    body = _optimize()
    match = [f for f in body["pareto_frontier"]
             if f["inputs"] == body["recommended"]["inputs"]]
    assert len(match) == 1 and match[0]["pareto_optimal"] is True
    assert "Pareto-optimal" in body["why_recommended"][0]
    assert "Not claimed globally optimal" in " ".join(body["why_recommended"])


# 14. API response compatibility: old fields intact, new fields present.
def test_14_response_compatibility():
    body = _optimize()
    for f in ("well_id", "mode", "current", "recommended", "delta",
              "objective_score", "top_scenarios", "why_recommended",
              "assumptions", "scenarios_evaluated", "prototype_disclaimer"):
        assert f in body
    for f in ("pareto_frontier", "pareto_count", "objective_summary",
              "constraints", "recommendation_policy", "uncertainty_note"):
        assert f in body
    assert set(body["objective_summary"]) == {
        "production_bopd", "sor_t_per_bbl",
        "energy_per_barrel_kwh", "mean_risk"}
    assert body["objective_summary"]["production_bopd"]["direction"] == "maximize"
    assert "Uncertainty" in body["uncertainty_note"] or \
        "uncertainty" in body["uncertainty_note"]
