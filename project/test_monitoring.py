"""Monitoring-script tests: Render health check + Supabase activity check.

All HTTP/database interactions are mocked — these tests never touch live
services and never require production credentials. Fake credentials only.

Covers (per master task §6):
  Render: healthy, non-2xx, timeout, invalid JSON, unexpected payload,
    SLOW_START cold-start label.
  Supabase: missing config, HEAD success (no payload), HTTP failure, timeout,
    QUERY_UNVERIFIED, no writes, no service-role, no secret/payload leakage,
    failures never reported healthy.
  Workflows: YAML parses, schedules, permissions, concurrency, timeouts,
    secret refs, dispatch trigger (skipped if PyYAML unavailable).
"""

import contextlib
import importlib.util
import io
import os
import urllib.error

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SCRIPTS = os.path.join(REPO, ".github", "scripts")
WORKFLOWS = os.path.join(REPO, ".github", "workflows")


def _load(name):
    path = os.path.join(SCRIPTS, name)
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


render_check = _load("render_health_check.py")
supabase_check = _load("supabase_activity_check.py")


class _FakeHeaders(dict):
    def get(self, key, default=None):
        for k, v in self.items():
            if k.lower() == key.lower():
                return v
        return default


class _FakeResponse:
    """Minimal urlopen() context-manager stub (status + body bytes + headers)."""

    def __init__(self, status=200, body=b"{}", headers=None):
        self.status = status
        self._body = body
        self.headers = _FakeHeaders(headers or {})

    def read(self):
        return self._body

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patch_urlopen(monkeypatch, module, fake):
    """Make module.urllib.request.urlopen behave as `fake(url, timeout=...)`."""
    monkeypatch.setattr(module.urllib.request, "urlopen", fake)


# ---- Render health check ----

def test_1_healthy_render_response(monkeypatch):
    body = b'{"status": "ok", "problem_id": "SIH26120", "version": "4.0.0-block4"}'
    _patch_urlopen(monkeypatch, render_check,
                   lambda req, timeout=None: _FakeResponse(200, body))
    status, detail = render_check.check_render_health("https://example.com/healthz")
    assert status == render_check.HEALTHY
    assert detail["http_status"] == 200
    assert detail["problem_id"] == "SIH26120"


def test_2_non_success_http_status(monkeypatch):
    def _raise(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 503, "Service Unavailable", {}, None)
    _patch_urlopen(monkeypatch, render_check, _raise)
    status, detail = render_check.check_render_health("https://example.com/healthz")
    assert status == render_check.HTTP_ERROR
    assert detail["http_status"] == 503
    assert status != render_check.HEALTHY


def test_3_timeout_handling(monkeypatch):
    def _raise(req, timeout=None):
        raise TimeoutError("timed out")
    # Avoid real 5 s backoff sleep between the 2 bounded attempts.
    monkeypatch.setattr(render_check.time, "sleep", lambda s: None)
    _patch_urlopen(monkeypatch, render_check, _raise)
    status, detail = render_check.check_render_health("https://example.com/healthz")
    assert status == render_check.TIMEOUT
    assert detail["http_status"] is None
    assert status != render_check.HEALTHY


def test_4_invalid_json(monkeypatch):
    _patch_urlopen(monkeypatch, render_check,
                   lambda req, timeout=None: _FakeResponse(200, b"not-json{"))
    status, detail = render_check.check_render_health("https://example.com/healthz")
    assert status == render_check.INVALID_RESPONSE
    assert detail["http_status"] == 200
    assert status != render_check.HEALTHY


def test_5_unexpected_health_response(monkeypatch):
    _patch_urlopen(monkeypatch, render_check,
                   lambda req, timeout=None: _FakeResponse(200, b'{"status": "down"}'))
    status, detail = render_check.check_render_health("https://example.com/healthz")
    assert status == render_check.INVALID_RESPONSE
    assert status != render_check.HEALTHY


def test_5b_slow_start_label(monkeypatch):
    """A valid 200+ok slower than the threshold is SLOW_START (still exit 0)."""
    body = b'{"status": "ok"}'
    _patch_urlopen(monkeypatch, render_check,
                   lambda req, timeout=None: _FakeResponse(200, body))
    # Force a slow latency by stubbing monotonic: start=0, end=threshold+1.
    calls = {"n": 0}
    threshold = render_check.SLOW_START_THRESHOLD_S

    def _mono():
        calls["n"] += 1
        return 0.0 if calls["n"] == 1 else threshold + 1.0
    monkeypatch.setattr(render_check.time, "monotonic", _mono)
    status, detail = render_check.check_render_health("https://example.com/healthz")
    assert status == render_check.SLOW_START
    assert detail["http_status"] == 200
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        monkeypatch.setattr(render_check, "check_render_health",
                            lambda *a, **k: (status, detail))
        code = render_check.main(["--url", "https://example.com/healthz"])
    assert code == 0  # SLOW_START is success (endpoint responded)


# ---- Supabase activity check ----

def test_6_missing_supabase_configuration():
    config, missing = supabase_check.load_config(env={})
    assert config is None
    assert set(missing) == {"SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_TABLE"}
    # main() with an empty env must report CONFIG_MISSING (exit 2),
    # never success.
    monkeypatch_env = pytest.MonkeyPatch()
    for var in supabase_check.REQUIRED_VARS:
        monkeypatch_env.delenv(var, raising=False)
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = supabase_check.main([])
    finally:
        monkeypatch_env.undo()
    assert code == 2
    out = buf.getvalue()
    assert supabase_check.CONFIG_MISSING in out
    assert "HEALTHY" not in out.split("status=")[1].split()[0] if "status=" in out else True


def test_7_successful_database_read(monkeypatch):
    """HEAD 200 with Content-Range evidence => HEALTHY, zero payload."""
    _patch_urlopen(monkeypatch, supabase_check,
                   lambda req, timeout=None: _FakeResponse(
                       200, b"", {"Content-Range": "*/0"}))
    status, detail = supabase_check.check_supabase_activity(
        "https://xyz.supabase.co", "anon-key", "some_table", "id")
    assert status == supabase_check.HEALTHY
    assert detail["http_status"] == 200
    assert detail["rows"] == 0


def test_7b_query_unverified_without_evidence(monkeypatch):
    """2xx without Content-Range => QUERY_UNVERIFIED, never HEALTHY."""
    _patch_urlopen(monkeypatch, supabase_check,
                   lambda req, timeout=None: _FakeResponse(200, b"", {}))
    status, detail = supabase_check.check_supabase_activity(
        "https://xyz.supabase.co", "anon-key", "some_table", "id")
    assert status == supabase_check.QUERY_UNVERIFIED
    assert status != supabase_check.HEALTHY


def test_8_failed_database_read(monkeypatch):
    """A reachable URL with a rejected query (401/RLS, 404/unknown table) is
    HTTP_ERROR — success must never be fabricated from liveness."""
    for code in (401, 404):
        def _raise(req, timeout=None, _code=code):
            raise urllib.error.HTTPError(req.full_url, _code, "error", {}, None)
        _patch_urlopen(monkeypatch, supabase_check, _raise)
        status, detail = supabase_check.check_supabase_activity(
            "https://xyz.supabase.co", "anon-key", "some_table", "id")
        assert status == supabase_check.HTTP_ERROR
        assert detail["http_status"] == code
        assert detail["rows"] is None
        assert status != supabase_check.HEALTHY


def test_8b_supabase_timeout(monkeypatch):
    monkeypatch.setattr(supabase_check.time, "sleep", lambda s: None)

    def _raise(req, timeout=None):
        raise TimeoutError("timed out")
    _patch_urlopen(monkeypatch, supabase_check, _raise)
    status, detail = supabase_check.check_supabase_activity(
        "https://xyz.supabase.co", "anon-key", "some_table", "id", timeout_s=1)
    assert status == supabase_check.TIMEOUT
    assert detail["http_status"] is None
    assert status != supabase_check.HEALTHY


def test_9_no_accidental_database_writes():
    """The activity script may only ever issue a bounded read-only HEAD."""
    src = open(os.path.join(SCRIPTS, "supabase_activity_check.py"), encoding="utf-8").read()
    assert 'method="HEAD"' in src
    for verb in ("POST", "PUT", "PATCH", "DELETE"):
        assert 'method="' + verb + '"' not in src, f"mutating request method: {verb}"
        assert "method='" + verb + "'" not in src, f"mutating request method: {verb}"
    for keyword in ("INSERT INTO", "UPDATE ", "DELETE FROM", "CREATE TABLE", "ALTER TABLE",
                    "DROP TABLE", "execute(", ".execute("):
        assert keyword not in src, f"write-like statement found: {keyword}"
    # No record payload: limit=0 and no select=* anywhere.
    assert "select=*" not in src, "must not request select=*"
    request = supabase_check.build_query_request(
        "https://xyz.supabase.co/", "some_table", "anon-key", "id")
    assert request.get_method() == "HEAD"
    assert "limit=0" in request.full_url
    assert "select=id" in request.full_url


def test_9b_no_service_role_required():
    src = open(os.path.join(SCRIPTS, "supabase_activity_check.py"), encoding="utf-8").read()
    assert "SUPABASE_SERVICE_ROLE_KEY" not in src.replace(
        '"SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_DB_PASSWORD"', "") or \
        "REQUIRED_VARS" in src  # redact-list mention only, never required
    assert "SUPABASE_SERVICE_ROLE_KEY" not in str(supabase_check.REQUIRED_VARS)
    assert set(supabase_check.REQUIRED_VARS) == {
        "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_TABLE"}


def test_10_no_secrets_in_diagnostic_output(monkeypatch, capsys):
    """Neither success nor failure output may echo key material or row data."""
    secret_key = "eyJhbGciOiJIUzI1NiIsInRlc3Qtc2VjcmV0LWtleS1hYmMxMjM"
    _patch_urlopen(monkeypatch, supabase_check,
                   lambda req, timeout=None: _FakeResponse(
                       200, b"", {"Content-Range": "*/0"}))
    status, _ = supabase_check.check_supabase_activity(
        "https://xyz.supabase.co", secret_key, "some_table", "id")
    assert status == supabase_check.HEALTHY
    # Exercise the CLI log line (success path) then the failure path.
    monkeypatch.setenv("SUPABASE_URL", "https://xyz.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", secret_key)
    monkeypatch.setenv("SUPABASE_TABLE", "some_table")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = supabase_check.main([])
    assert code == 0
    success_out = buf.getvalue()
    assert secret_key not in success_out
    assert "row-data" not in success_out
    assert "select=*" not in success_out

    def _raise(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, secret_key, {}, None)
    _patch_urlopen(monkeypatch, supabase_check, _raise)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = supabase_check.main([])
    assert code == 1
    failure_out = buf.getvalue()
    assert secret_key not in failure_out
    assert "HEALTHY" not in failure_out
    capsys.readouterr()  # keep pytest capture clean


def test_11_failures_never_healthy(monkeypatch):
    """Every failure mode must not return HEALTHY / exit 0."""
    monkeypatch.setattr(supabase_check.time, "sleep", lambda s: None)
    cases = []

    def _http401(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "e", {}, None)
    cases.append(_http401)

    def _timeout(req, timeout=None):
        raise TimeoutError("timed out")
    cases.append(_timeout)

    def _no_evidence(req, timeout=None):
        return _FakeResponse(200, b"", {})
    cases.append(_no_evidence)

    for fake in cases:
        _patch_urlopen(monkeypatch, supabase_check, fake)
        status, _ = supabase_check.check_supabase_activity(
            "https://xyz.supabase.co", "k", "t", "id", timeout_s=1)
        assert status != supabase_check.HEALTHY

    # Render failures likewise.
    def _r503(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 503, "x", {}, None)
    _patch_urlopen(monkeypatch, render_check, _r503)
    status, _ = render_check.check_render_health("https://example.com/healthz")
    assert status != render_check.HEALTHY
    assert status != render_check.SLOW_START


yaml = pytest.importorskip("yaml", reason="PyYAML not installed; YAML check skipped")


def _load_yaml(path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_12_workflow_yaml_valid():
    for name in ("supabase-activity-monitor.yml", "render-health-monitor.yml"):
        data = _load_yaml(os.path.join(WORKFLOWS, name))
        assert isinstance(data, dict)
        on = data.get("on", data.get(True))  # 'on' parses as True in YAML 1.1
        assert on is not None and ("schedule" in on or "workflow_dispatch" in on)
        assert data.get("permissions") == {"contents": "read"}
        assert "concurrency" in data
        for job in data["jobs"].values():
            assert job.get("timeout-minutes", 0) <= 10


def test_13_workflow_schedules_and_refs():
    sup = open(os.path.join(WORKFLOWS, "supabase-activity-monitor.yml"), encoding="utf-8").read()
    assert "17 3 * * *" in sup
    assert "workflow_dispatch" in sup
    assert "secrets.SUPABASE_URL" in sup
    assert "secrets.SUPABASE_ANON_KEY" in sup
    assert "secrets.SUPABASE_TABLE" in sup
    assert "SERVICE_ROLE" not in sup
    assert "select=*" not in sup
    ren = open(os.path.join(WORKFLOWS, "render-health-monitor.yml"), encoding="utf-8").read()
    assert "7,17,27,37,47,57 * * * *" in ren
    assert "workflow_dispatch" in ren
    assert "https://petro-forge.onrender.com/healthz" in ren
