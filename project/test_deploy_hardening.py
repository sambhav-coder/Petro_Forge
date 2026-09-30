"""Deployment hardening tests: explicit CORS, /healthz, config validation,
frontend env-safety guardrails, endpoint compatibility."""

import importlib.util
import os
import re

import pytest
from fastapi.testclient import TestClient

import deploy_config

app_path = os.path.join(os.path.dirname(__file__), "app.py")
spec = importlib.util.spec_from_file_location("app_sih26120_deploy", app_path)
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)
client = TestClient(app_module.app)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PROD_ORIGIN = "https://petro-forge.vercel.app"


@pytest.fixture(autouse=True)
def _clean():
    app_module.reset_block1_state()
    yield
    app_module.reset_block1_state()


# ---- config validation ----
def test_1_defaults_include_production_no_wildcard():
    origins = deploy_config.resolve_cors_origins(None)
    assert PROD_ORIGIN in origins
    assert "*" not in origins
    assert all(o.startswith(("http://", "https://")) for o in origins)


def test_2_custom_origins_parsed_and_deduped():
    origins = deploy_config.resolve_cors_origins(
        "https://petro-forge.vercel.app, https://example.com:3000 ,"
        "https://petro-forge.vercel.app")
    assert origins == ["https://petro-forge.vercel.app", "https://example.com:3000"]


def test_3_malformed_origins_rejected():
    for bad in ("not-a-url", "https://host/path", "http://host?q=1",
                "ftp://host", "https://", "*, https://a.com"):
        with pytest.raises(ValueError):
            deploy_config.resolve_cors_origins(bad)


def test_4_empty_config_rejected():
    with pytest.raises(ValueError):
        deploy_config.resolve_cors_origins("  ,  ")


# ---- live CORS behavior (not just helpers) ----
def test_5_production_origin_allowed():
    r = client.get("/healthz", headers={"Origin": PROD_ORIGIN})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == PROD_ORIGIN


def test_6_unrelated_origin_rejected():
    r = client.get("/healthz", headers={"Origin": "https://example.com"})
    assert r.status_code == 200  # resource still served...
    assert "access-control-allow-origin" not in r.headers  # ...but not CORS-shared


def test_7_preflight_allows_production_denies_other():
    pre = {"Origin": PROD_ORIGIN, "Access-Control-Request-Method": "POST"}
    r = client.options("/api/v1/telemetry/ingest", headers=pre)
    assert r.headers.get("access-control-allow-origin") == PROD_ORIGIN
    pre = {"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"}
    r = client.options("/api/v1/telemetry/ingest", headers=pre)
    assert "access-control-allow-origin" not in r.headers


def test_8_local_dev_origin_allowed():
    r = client.get("/healthz", headers={"Origin": "http://localhost:3000"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_9_no_wildcard_or_credentials_in_cors():
    r = client.get("/healthz", headers={"Origin": PROD_ORIGIN})
    assert r.headers.get("access-control-allow-origin") != "*"
    # No cookie/token auth is used, so credentials must stay off.
    assert r.headers.get("access-control-allow-credentials") is None


# ---- health ----
def test_10_healthz_lightweight():
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["problem_id"] == "SIH26120"


def test_11_root_unchanged():
    body = client.get("/").json()
    assert body["problem_id"] == "SIH26120"
    assert body["status"] == "OPERATIONAL"


# ---- frontend env-safety guardrails ----
def test_12_no_unchecked_localhost_fallback():
    """Exactly one localhost reference may exist in the API layer, and it
    must sit behind the production-missing-env guard."""
    lib = os.path.join(REPO, "frontend", "lib")
    hits = []
    for name in os.listdir(lib):
        if not name.endswith((".ts", ".tsx")):
            continue
        src = open(os.path.join(lib, name), encoding="utf-8").read()
        for i, line in enumerate(src.splitlines(), 1):
            if "127.0.0.1" in line or "localhost" in line:
                hits.append((name, i, line.strip()))
    assert hits, "expected the guarded local fallback to exist"
    files = {h[0] for h in hits}
    assert files == {"api.ts"}, f"localhost refs outside api.ts: {hits}"
    api_src = open(os.path.join(lib, "api.ts"), encoding="utf-8").read()
    assert "NEXT_PUBLIC_API_BASE_URL is not configured" in api_src
    assert "isLocalHostname" in api_src


def test_13_no_hardcoded_prod_url_in_calls():
    lib = os.path.join(REPO, "frontend", "lib", "api.ts")
    src = open(lib, encoding="utf-8").read()
    calls = [l for l in src.splitlines()
             if ("fetch(" in l or "EventSource" in l or "apiBase()" in l)]
    assert calls, "API layer must route through the central apiBase mechanism"
    assert "petro-forge.onrender.com" not in src or "production:" in src


# ---- representative compatibility ----
def test_14_representative_endpoints_ok():
    assert client.get("/docs").status_code == 200
    assert client.get("/api/v1/ml/status").status_code == 200
    payload = {"well_id": "BGW-01", "reservoir_temperature_c": 60.0,
               "reservoir_pressure_bar": 30.0, "api_gravity": 18.0,
               "wellhead_pressure_bar": 12.0, "oil_rate_bopd": 40.0,
               "steam_volume_t": 900.0, "steam_injection_pressure_bar": 65.0,
               "soak_time_h": 48.0, "css_phase": "PRODUCTION", "spm": 6.0,
               "stroke_in": 96.0, "vfd_percent": 55.0}
    assert client.post("/api/v1/telemetry/ingest", json=payload).status_code == 201
    assert "pump_performance" in client.get("/api/v1/wells/BGW-01/dynacard").json()
    multi = client.post("/api/v1/wells/BGW-01/cycle/multi", json={"cycles": 1}).json()
    assert multi["cumulative"]["cycles_simulated"] == 1
    auto = client.post("/api/v1/wells/BGW-01/optimize", json={}).json()
    assert auto["pareto_count"] >= 1
    assert client.get("/api/v1/alerts?limit=5").status_code == 200
    assert client.get("/api/v1/field/overview").status_code == 200
    assert re.match(r"^\d+\.\d+\.\d+", client.get("/").json()["version"])
