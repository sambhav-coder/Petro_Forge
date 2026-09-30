"""P6 multi-cycle CSS intelligence tests: single-cycle compat, sequential
state, cumulative metrics, determinism, validation, recommendation,
historical-insufficient state, provenance, API contracts."""

import importlib.util
import os

import pytest
from fastapi.testclient import TestClient

import css_cycle

app_path = os.path.join(os.path.dirname(__file__), "app.py")
spec = importlib.util.spec_from_file_location("app_sih26120_multicycle", app_path)
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


def _ingest(**over):
    r = client.post("/api/v1/telemetry/ingest", json=_payload(**over))
    assert r.status_code == 201


def _multi(**body):
    _ingest()
    r = client.post("/api/v1/wells/BGW-01/cycle/multi", json=body or {"cycles": 3})
    assert r.status_code == 200, r.text[:300]
    return r.json()


# 1. Existing single-cycle behavior unchanged.
def test_1_single_cycle_compat():
    _ingest()
    cyc = client.get("/api/v1/wells/BGW-01/cycle").json()
    plan = client.post("/api/v1/wells/BGW-01/cycle/plan", json={}).json()
    for f in ("cycle_oil_bbl", "optimal_cutoff_production_day", "cycle_sor_cwe",
              "series", "explanation"):
        assert f in cyc
    assert plan["recommended"]["steam_volume_t"] in css_cycle.PLAN_STEAM_T
    assert plan["candidates_evaluated"] == 25


# 2-3. Single + multiple sequential cycles.
def test_2_single_multicycle_run():
    body = _multi(cycles=1)
    assert len(body["cycles"]) == 1
    assert body["cycles"][0]["cycle_number"] == 1
    assert body["cumulative"]["cycles_simulated"] == 1


def test_3_three_sequential_cycles():
    body = _multi(cycles=3)
    assert [c["cycle_number"] for c in body["cycles"]] == [1, 2, 3]
    for c in body["cycles"]:
        for f in ("planned", "state_in", "state_out", "cycle_oil_bbl",
                  "cycle_steam_t", "cycle_sor_cwe", "average_cycle_rate_bopd",
                  "peak_heated_temperature_c"):
            assert f in c


# 4. State propagation N -> N+1 (pressure depletes, heat carries).
def test_4_state_propagation():
    body = _multi(cycles=3)
    pressures = [body["initial_state"]["reservoir_pressure_bar"]] + \
                [c["state_out"]["reservoir_pressure_bar"] for c in body["cycles"]]
    assert all(b < a for a, b in zip(pressures, pressures[1:])), pressures
    for i, c in enumerate(body["cycles"]):
        prev_out = body["cycles"][i - 1]["state_out"] if i else body["initial_state"]
        assert c["state_in"]["reservoir_pressure_bar"] == prev_out["reservoir_pressure_bar"]
        assert c["state_in"]["reservoir_temperature_c"] == prev_out["reservoir_temperature_c"]
    assert body["linkage"]["pressure_depletion_bar_per_bbl"] == \
        css_cycle.PRESSURE_DEPLETION_BAR_PER_BBL
    assert body["linkage"]["heat_carryover_frac"] == css_cycle.HEAT_CARRYOVER_FRAC


# 5-7. Cumulative oil / steam / SOR are exact sums/ratios.
def test_5_cumulative_oil_sums_cycles():
    body = _multi(cycles=3)
    assert body["cumulative"]["total_oil_bbl"] == \
        pytest.approx(sum(c["cycle_oil_bbl"] for c in body["cycles"]), abs=0.2)


def test_6_cumulative_steam_sums_planned():
    body = _multi(cycles=3)
    assert body["cumulative"]["total_steam_t"] == \
        pytest.approx(sum(c["cycle_steam_t"] for c in body["cycles"]), abs=1e-9)


def test_7_cumulative_sor_is_ratio_of_totals():
    body = _multi(cycles=3)
    cum = body["cumulative"]
    assert cum["cumulative_sor_cwe"] == \
        pytest.approx(cum["total_steam_t"] * css_cycle.BBL_CWE_PER_T / cum["total_oil_bbl"],
                      rel=1e-3)


# 8. Deterministic results.
def test_8_deterministic():
    a = _multi(cycles=3)
    app_module.reset_block1_state()
    b = _multi(cycles=3)
    assert a["cycles"] == b["cycles"]
    assert a["cumulative"] == b["cumulative"]
    assert a["recommendation"] == b["recommendation"]


# 9-10. Zero/invalid cycle counts and invalid parameters -> 422.
def test_9_zero_and_excess_cycles_rejected():
    _ingest()
    assert client.post("/api/v1/wells/BGW-01/cycle/multi",
                       json={"cycles": 0}).status_code == 422
    assert client.post("/api/v1/wells/BGW-01/cycle/multi",
                       json={"cycles": 7}).status_code == 422


def test_10_invalid_sor_limit_rejected():
    _ingest()
    assert client.post("/api/v1/wells/BGW-01/cycle/multi",
                       json={"cycles": 2, "sor_limit_cwe": -1.0}).status_code == 422


# 11-12. Recommendation generation + explanation.
def test_11_recommendation_present():
    body = _multi(cycles=2)
    rec = body["recommendation"]
    assert rec["next_cycle_number"] == 3
    assert rec["steam_volume_t"] in css_cycle.PLAN_STEAM_T
    assert rec["soak_time_h"] in css_cycle.PLAN_SOAK_H
    assert rec["optimal_cutoff_production_day"] >= 1


def test_12_recommendation_explained_without_global_claim():
    body = _multi(cycles=2)
    text = " ".join(body["recommendation"]["reasons"])
    assert "prototype" in text.lower()
    # Any optimality language must be an explicit denial, never a claim.
    assert "Not claimed globally optimal" in text
    assert body["recommendation"]["policy"] == css_cycle.MULTI_POLICY


# 13. Historical-data insufficient state (BGW-01: no CSS history).
def test_13_historical_insufficient_state():
    body = _multi(cycles=2)
    hist = body["historical_context"]
    assert hist["status"] == "INSUFFICIENT_DATA"
    assert hist["usable_response_data"] is False
    assert hist["prior_css_events"] == 0


# 14. Provenance metadata explicit.
def test_14_provenance_metadata():
    body = _multi(cycles=2)
    assert body["mode"] == css_cycle.MULTI_MODE_LABEL
    assert body["data_mode"] == "PROTOTYPE_SIMULATION"
    assert "prototype" in body["prototype_disclaimer"].lower()
    assert any("prototype" in lim.lower() for lim in body["limitations"])
    assert "NOT Baghewala-calibrated" in body["linkage"]["note"]


# 15-16. Existing CSS API compatibility + multi-cycle response shape.
def test_15_existing_css_api_compat():
    _ingest()
    assert "optimal_cutoff_production_day" in \
        client.get("/api/v1/wells/BGW-01/cycle").json()
    assert "recommended" in client.post("/api/v1/wells/BGW-01/cycle/plan",
                                        json={}).json()


def test_16_multicycle_response_shape():
    body = _multi(cycles=3)
    for f in ("well_id", "mode", "data_mode", "cycles_requested",
              "initial_state", "linkage", "historical_context", "cycles",
              "cumulative", "recommendation", "limitations",
              "prototype_disclaimer"):
        assert f in body
