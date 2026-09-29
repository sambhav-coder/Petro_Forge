"""
Automated Pytest Suite for SIH26120 FastAPI Microservice — Block 1.

Covers the original 5 regression areas (adapted where the generic
scalar telemetry contract was intentionally replaced by the
well-centric contract) plus the Block 1 acceptance behaviors:
validation, well independence, deterministic stats, no fake AI fields.
"""

import os
import importlib.util
import pytest
from fastapi.testclient import TestClient

app_path = os.path.join(os.path.dirname(__file__), "app.py")
spec = importlib.util.spec_from_file_location("app_sih26120", app_path)
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


# ---- Original regression areas (contracts updated for Block 1) ----

def test_health_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["problem_id"] == "SIH26120"
    assert data["status"] == "OPERATIONAL"
    assert "timestamp" in data


def test_stats_endpoint():
    # Empty store: deterministic zero values, honest non-optimal health.
    response = client.get("/api/v1/telemetry/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_wells"] == 0
    assert data["active_wells"] == 0
    assert data["average_oil_rate_bopd"] == 0.0
    assert data["system_health"] == "NO_DATA"


def test_telemetry_ingest():
    response = client.post("/api/v1/telemetry/ingest", json=make_payload())
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "TELEMETRY_ACCEPTED"
    assert data["well_id"] == "BGW-01"
    assert data["well_state"]["oil_rate_bopd"] == 22.5
    assert data["well_state"]["css_phase"] == "PRODUCTION"
    assert "sha256_hash" in data
    # Block 1 must not return fake AI fields.
    assert "risk_score" not in data
    assert "confidence" not in data
    assert "risk_score" not in data["well_state"]
    assert "confidence" not in data["well_state"]


def test_audit_logs():
    client.post("/api/v1/telemetry/ingest", json=make_payload())
    response = client.get("/api/v1/audit/logs")
    assert response.status_code == 200
    data = response.json()
    assert "total_records" in data
    assert isinstance(data["records"], list)
    assert data["total_records"] >= 1


def test_dispatch_action():
    payload = {
        "event_id": "EVT-999888",
        "protocol_type": "URGENT_OPERATIONAL_ESCALATION",
        "notes": "Automated pipeline trigger"
    }
    response = client.post("/api/v1/action/dispatch", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["event_id"] == "EVT-999888"
    assert data["status"] == "DISPATCHED_TO_FIELD_TEAMS"


# ---- Block 1: validation ----

def test_valid_baghewala_payload_accepted():
    payload = make_payload(
        well_id="BGW-02",
        reservoir_temperature_c=46.5,
        api_gravity=17.5,
        css_phase="SOAK",
    )
    response = client.post("/api/v1/telemetry/ingest", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["well_state"]["well_id"] == "BGW-02"
    assert data["well_state"]["api_gravity"] == 17.5
    assert data["well_state"]["css_phase"] == "SOAK"


def test_invalid_negative_pressure_rejected():
    response = client.post(
        "/api/v1/telemetry/ingest", json=make_payload(reservoir_pressure_bar=-5.0)
    )
    assert response.status_code == 422


def test_invalid_vfd_rejected():
    response = client.post("/api/v1/telemetry/ingest", json=make_payload(vfd_percent=150.0))
    assert response.status_code == 422


def test_invalid_water_cut_rejected():
    response = client.post(
        "/api/v1/telemetry/ingest", json=make_payload(water_cut_percent=120.0)
    )
    assert response.status_code == 422


def test_invalid_css_phase_rejected():
    response = client.post("/api/v1/telemetry/ingest", json=make_payload(css_phase="BOILING"))
    assert response.status_code == 422


# ---- Block 1: well store behavior ----

def test_well_creation_and_update():
    client.post("/api/v1/telemetry/ingest", json=make_payload(oil_rate_bopd=20.0))
    updated = make_payload(oil_rate_bopd=27.5, timestamp="2026-09-29T12:00:00+00:00")
    response = client.post("/api/v1/telemetry/ingest", json=updated)
    assert response.status_code == 201

    fetched = client.get("/api/v1/wells/BGW-01")
    assert fetched.status_code == 200
    assert fetched.json()["oil_rate_bopd"] == 27.5
    assert fetched.json()["timestamp"] == "2026-09-29T12:00:00+00:00"


def test_multiple_wells_independent():
    client.post("/api/v1/telemetry/ingest", json=make_payload("BGW-01", oil_rate_bopd=20.0))
    client.post("/api/v1/telemetry/ingest", json=make_payload("BGW-02", oil_rate_bopd=31.0))

    w1 = client.get("/api/v1/wells/BGW-01").json()
    w2 = client.get("/api/v1/wells/BGW-02").json()
    assert w1["oil_rate_bopd"] == 20.0
    assert w2["oil_rate_bopd"] == 31.0

    # Updating one well must not touch the other.
    client.post(
        "/api/v1/telemetry/ingest",
        json=make_payload("BGW-01", oil_rate_bopd=99.0, timestamp="2026-09-29T14:00:00+00:00"),
    )
    assert client.get("/api/v1/wells/BGW-01").json()["oil_rate_bopd"] == 99.0
    assert client.get("/api/v1/wells/BGW-02").json()["oil_rate_bopd"] == 31.0


def test_list_wells():
    client.post("/api/v1/telemetry/ingest", json=make_payload("BGW-01", oil_rate_bopd=20.0))
    client.post("/api/v1/telemetry/ingest", json=make_payload("BGW-02", oil_rate_bopd=30.0))
    response = client.get("/api/v1/wells")
    assert response.status_code == 200
    data = response.json()
    assert data["total_wells"] == len({"BGW-01", "BGW-02"} | set(app_module.PUBLIC_WELLS))
    by_id = {w["well_id"]: w for w in data["wells"]}
    assert by_id["BGW-01"]["oil_rate_bopd"] == 20.0
    assert by_id["BGW-01"]["data_status"] == "LIVE_TELEMETRY"  # telemetry supersedes public
    # Public registry wells are present with null telemetry (never fabricated).
    assert by_id["BGW-08"]["data_status"] == "PUBLIC_FIELD_RECORD"
    assert by_id["BGW-08"]["provenance"] == "BAGHEWALA_FIELD"
    assert by_id["BGW-08"]["oil_rate_bopd"] is None
    assert by_id["BGW-02"]["spm"] == 5.0
    assert by_id["BGW-02"]["stroke_in"] == 96.0
    assert by_id["BGW-01"]["css_phase"] == "PRODUCTION"
    assert "last_update" in by_id["BGW-01"]


def test_get_well_by_id():
    client.post("/api/v1/telemetry/ingest", json=make_payload("BGW-07", spm=6.5))
    response = client.get("/api/v1/wells/BGW-07")
    assert response.status_code == 200
    data = response.json()
    assert data["well_id"] == "BGW-07"
    assert data["spm"] == 6.5
    assert data["stroke_in"] == 96.0


def test_unknown_well_returns_404():
    response = client.get("/api/v1/wells/BGW-UNKNOWN")
    assert response.status_code == 404
    assert "BGW-UNKNOWN" in response.json()["detail"]


# ---- Block 1: determinism ----

def test_stats_deterministic_with_correct_averages():
    client.post(
        "/api/v1/telemetry/ingest",
        json=make_payload(
            "BGW-01",
            oil_rate_bopd=20.0,
            reservoir_temperature_c=47.0,
            wellhead_pressure_bar=12.0,
            timestamp="2026-09-29T10:00:00+00:00",
        ),
    )
    client.post(
        "/api/v1/telemetry/ingest",
        json=make_payload(
            "BGW-02",
            oil_rate_bopd=30.0,
            reservoir_temperature_c=49.0,
            wellhead_pressure_bar=14.0,
            timestamp="2026-09-29T11:00:00+00:00",
        ),
    )
    first = client.get("/api/v1/telemetry/stats").json()
    second = client.get("/api/v1/telemetry/stats").json()
    assert first == second
    assert first["total_wells"] == 2
    assert first["average_oil_rate_bopd"] == 25.0
    assert first["average_reservoir_temperature_c"] == 48.0
    assert first["average_wellhead_pressure_bar"] == 13.0
    assert first["last_sync"] == "2026-09-29T11:00:00+00:00"


def test_repeated_identical_telemetry_deterministic_state():
    first = client.post("/api/v1/telemetry/ingest", json=make_payload()).json()
    second = client.post("/api/v1/telemetry/ingest", json=make_payload()).json()
    assert first["well_state"] == second["well_state"]
    for payload in (first, second):
        assert "risk_score" not in payload
        assert "confidence" not in payload


def test_audit_contains_well_id():
    client.post("/api/v1/telemetry/ingest", json=make_payload("BGW-03"))
    records = client.get("/api/v1/audit/logs").json()["records"]
    assert len(records) >= 1
    assert records[-1]["well_id"] == "BGW-03"
    assert "sha256_hash" in records[-1]


def test_no_landslide_residue_in_api_metadata():
    root = client.get("/").json()
    stats = client.get("/api/v1/telemetry/stats").json()
    for text in (root["domain"], stats["domain"], root["title"]):
        assert "Landslide" not in text
        assert "Slope Stability" not in text
        assert "GIS" not in text
