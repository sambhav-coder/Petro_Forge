"""Co-Pilot backend tests: session/analyze/simulate/ask contracts + safety.

Uses the FastAPI TestClient with seeded demo telemetry (no production data,
no credentials). Verifies simulation-only behaviour: WELL_STORE/HISTORY are
byte-identical after simulate calls and no control endpoint is reachable.
"""

import copy

from fastapi.testclient import TestClient

import app as app_module


def _client():
    return TestClient(app_module.app)


def _seed():
    c = _client()
    r = c.post("/api/v1/demo/seed", json={"days": 5})
    assert r.status_code in (200, 201), r.text
    wells = c.get("/api/v1/wells").json()["wells"]
    live = [w for w in wells if w.get("data_status") != "PUBLIC_FIELD_RECORD"]
    assert live, "seed must create live wells"
    return c, live[0]["well_id"]


def _store_snapshot():
    return (copy.deepcopy(dict(app_module.WELL_STORE)),
            copy.deepcopy({k: list(v) for k, v in app_module.HISTORY.items()}))


def test_session_ok():
    c, wid = _seed()
    r = c.post("/api/v1/copilot/session", json={"well_id": wid})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["well_id"] == wid and body["simulation_only"] is True
    assert body["session_id"].startswith("cpl-")
    assert body["mode"] in ("FALLBACK_TEMPLATE", "LLM")
    assert isinstance(body["stages"], list) and "baseline" in body["stages"]
    assert isinstance(body["findings"], list) and body["findings"]
    assert "hi" in body["narration"]["language"].lower() or "hinglish" in body["narration"]["language"].lower()


def test_session_unknown_well_404():
    c, _ = _seed()
    r = c.post("/api/v1/copilot/session", json={"well_id": "NOPE-999"})
    assert r.status_code == 404


def test_analyze_findings_have_provenance():
    c, wid = _seed()
    r = c.post("/api/v1/copilot/analyze", json={"well_id": wid})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["simulation_only"] is True
    for f in body["findings"]:
        for k in ("finding_id", "well_id", "title", "severity", "explanation",
                  "provenance", "limitations"):
            assert k in f, f"missing {k}"
        assert f["well_id"] == wid


def test_simulate_valid_and_no_mutation():
    c, wid = _seed()
    before = _store_snapshot()
    base = c.get(f"/api/v1/wells/{wid}/twin").json()
    sc = {"spm": max(1.0, min(8.0, (base.get("spm") or 5.0) + 1.0))}
    r = c.post("/api/v1/copilot/simulate", json={"well_id": wid, "scenarios": [sc]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["simulation_only"] is True
    assert body["baseline_label"] == "OBSERVED_BASELINE"
    assert len(body["simulations"]) == 1
    assert body["simulations"][0]["label"] == "SIMULATION"
    after = _store_snapshot()
    assert before[0].keys() == after[0].keys()
    for k in before[0]:
        assert before[0][k] == after[0][k]
    assert {k: len(v) for k, v in before[1].items()} == {k: len(v) for k, v in after[1].items()}


def test_simulate_bounds_and_limits():
    c, wid = _seed()
    assert c.post("/api/v1/copilot/simulate",
                  json={"well_id": wid, "scenarios": [{"spm": 99.0}]}).status_code == 422
    assert c.post("/api/v1/copilot/simulate",
                  json={"well_id": wid, "scenarios": [{"nope_field": 1}]}).status_code == 422
    many = [{"spm": 5.0}, {"spm": 6.0}, {"spm": 7.0}, {"spm": 8.0}]
    assert c.post("/api/v1/copilot/simulate",
                  json={"well_id": wid, "scenarios": many}).status_code == 422


def test_ask_refuses_control_and_grounds():
    c, wid = _seed()
    r = c.post("/api/v1/copilot/ask",
               json={"well_id": wid, "question": "Please open the valve via SCADA now"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["simulation_only"] is True
    assert "SCADA" in body["answer"] or "operate" in body["answer"].lower()
    assert set(body["allowed_tools"]) <= set(__import__("copilot").ALLOWED_TOOLS)
    r2 = c.post("/api/v1/copilot/ask",
                json={"well_id": wid, "question": "Well ki current condition kya hai?"})
    assert r2.status_code == 200 and r2.json()["evidence_refs"]


def test_no_secrets_or_control_surface():
    c, wid = _seed()
    for payload, path in (
        ({"well_id": wid}, "/api/v1/copilot/session"),
        ({"well_id": wid}, "/api/v1/copilot/analyze"),
        ({"well_id": wid, "question": "hi"}, "/api/v1/copilot/ask"),
        ({"well_id": wid}, "/api/v1/copilot/plan"),
    ):
        text = c.post(path, json=payload).text.lower()
        assert "api_key" not in text and "service_role" not in text
    # No physical-control endpoints exist.
    routes = [r.path for r in app_module.app.routes]
    assert not any(x in p for p in routes for x in ("/control", "/scada", "/actuat", "/valve"))


def test_plan_full_coverage_live_well():
    c, wid = _seed()
    before = _store_snapshot()
    r = c.post("/api/v1/copilot/plan", json={"well_id": wid})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["simulation_only"] is True
    segs = body["segments"]
    assert len(segs) == 10
    # Ordered, unique, schema-complete segments.
    assert [s["sequence"] for s in segs] == list(range(1, 11))
    for s in segs:
        for k in ("segment_id", "stage", "title", "narration_text", "spoken_text",
                  "speech_chunks", "component_focus", "camera_action",
                  "available", "completion_condition"):
            assert k in s, f"segment missing {k}"
        assert s["completion_condition"] == "audio_end"
        assert s["speech_chunks"], "each segment must speak"
        assert "cpl-" not in s["spoken_text"] and "{" not in s["spoken_text"]
    avail = [s for s in segs if s["available"]]
    assert len(avail) >= 7, "seeded live well must support most chapters"
    assert body["coverage"]["available"] == len(avail)
    # Camera actions only reference real presets.
    assert {s["camera_action"] for s in segs} <= {"FIELD", "WELL", "WELLBORE", "RESERVOIR", "PUMP"}
    after = _store_snapshot()
    assert before[0].keys() == after[0].keys()


def test_plan_public_well_skips_honestly():
    c, _ = _seed()
    wells = c.get("/api/v1/wells").json()["wells"]
    pub = [w for w in wells if w.get("data_status") == "PUBLIC_FIELD_RECORD"]
    if not pub:
        return
    body = c.post("/api/v1/copilot/plan", json={"well_id": pub[0]["well_id"]}).json()
    skipped = {s["stage"] for s in body["segments"] if not s["available"]}
    assert {"telemetry", "hybrid", "srp", "simulation"} <= skipped
    for s in body["segments"]:
        if not s["available"]:
            assert s["unavailable_reason"], "skips need reasons"


def test_plan_unknown_well_404():
    c, _ = _seed()
    assert c.post("/api/v1/copilot/plan", json={"well_id": "NOPE-999"}).status_code == 404


def test_speech_helpers_no_ids_or_json():
    import copilot as cp
    chunks = cp.chunk_text("First sentence here. Second one is longer and keeps going, with commas, to test splitting.", max_len=40)
    assert len(chunks) >= 2 and all(len(x) <= 60 for x in chunks)
    spoken = cp.to_speech_text("Well cpl-abcdef1234 at 2026-10-15T09:00:00Z runs 5 SPM, SOR 0.1, 22.5 bopd {\"a\":1}")
    assert "cpl-" not in spoken and "2026" not in spoken and "{" not in spoken
    assert "S P M" in spoken and "S O R" in spoken
    assert cp._phase("CSSPhase.INJECTION") == "INJECTION"
    assert cp._phase("PRODUCTION") == "PRODUCTION"


def test_narration_never_leaks_enum_repr():
    """Live finding/plan narration must show clean phase names (no CSSPhase.X)."""
    import copilot as cp
    ctx = {"well_id": "W-1",
           "telemetry": {"css_phase": "CSSPhase.INJECTION", "oil_rate_bopd": 0.0},
           "twin": {"estimated_oil_production_bopd": 1.0, "production_limiting_factor": "X"}}
    for f in cp.build_findings(ctx):
        assert "CSSPhase" not in f["explanation"]
    plan = cp.build_presentation_plan(ctx)
    for s in plan["segments"]:
        assert "CSSPhase" not in s["narration_text"]
        assert "CSSPhase" not in s["spoken_text"]


def test_plan_chapter_camera_and_panel_mapping():
    """Exact chapter → camera + panel contract (single authoritative timeline)."""
    c, wid = _seed()
    body = c.post("/api/v1/copilot/plan", json={"well_id": wid}).json()
    by_stage = {s["stage"]: s for s in body["segments"]}
    expected = {
        "welcome": ("FIELD", "OVERVIEW"), "model": ("FIELD", "OVERVIEW"),
        "telemetry": ("WELL", "TELEMETRY"), "hybrid": ("WELL", "HYBRID"),
        "srp": ("PUMP", "SRP"), "css": ("RESERVOIR", "CYCLE"),
        "alerts": ("FIELD", "OVERVIEW"), "simulation": ("PUMP", "WHAT-IF"),
        "optimization": ("FIELD", "OPTIMIZATION"), "summary": ("FIELD", "OVERVIEW"),
    }
    assert set(by_stage) == set(expected)
    for stage, (cam, tab) in expected.items():
        assert by_stage[stage]["camera_action"] == cam, stage
        assert by_stage[stage]["panel_tab"] == tab, stage
        assert by_stage[stage]["panel_section"] == f"copilot-{stage}", stage


def test_plan_srp_gated_on_dynacard():
    """SRP chapter is available only with dynacard evidence (no blind narration)."""
    c, wid = _seed()
    body = c.post("/api/v1/copilot/plan", json={"well_id": wid}).json()
    srp = next(s for s in body["segments"] if s["stage"] == "srp")
    assert srp["available"] is True
    assert "Dynacard" in srp["narration_text"] or "dynacard" in srp["narration_text"].lower()


def test_plan_values_match_evidence_no_fabrication():
    """Every related value in the plan must come from the context evidence."""
    c, wid = _seed()
    ctx = c.post("/api/v1/copilot/session", json={"well_id": wid}).json()
    plan = c.post("/api/v1/copilot/plan", json={"well_id": wid}).json()
    tele_oil = c.get(f"/api/v1/wells/{wid}").json()["oil_rate_bopd"]
    tele_seg = next(s for s in plan["segments"] if s["stage"] == "telemetry")
    oil_vals = [v for v in tele_seg["related_values"] if v["name"] == "oil_rate_bopd"]
    assert oil_vals and oil_vals[0]["value"] == tele_oil
    assert all(v["provenance"] in ("OBSERVED", "HISTORICAL", "DERIVED",
               "PHYSICS_PREDICTION", "CALIBRATED_TWIN", "SIMULATION",
               "SYNTHETIC_DEMO", "UNAVAILABLE") for s in plan["segments"] for v in s["related_values"])
