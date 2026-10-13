"""Monitoring-script tests: Render health check + Supabase activity check.

All HTTP/database interactions are mocked — these tests never touch live
services and never require production credentials. They cover:

 1. Healthy Render response              6. Missing Supabase configuration
 2. Non-success HTTP status              7. Successful database read
 3. Timeout handling                     8. Failed database read
 4. Invalid JSON                         9. No accidental database writes
 5. Unexpected health response          10. No secrets in diagnostic output
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


def _load(name):
    path = os.path.join(SCRIPTS, name)
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


render_check = _load("render_health_check.py")
supabase_check = _load("supabase_activity_check.py")


class _FakeResponse:
    """Minimal urlopen() context-manager stub (status + body bytes)."""

    def __init__(self, status=200, body=b"{}"):
        self.status = status
        self._body = body

    def read(self):
        return self._body

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
    assert status == render_check.UNAVAILABLE
    assert detail["http_status"] == 503


def test_3_timeout_handling(monkeypatch):
    def _raise(req, timeout=None):
        raise TimeoutError("timed out")
    _patch_urlopen(monkeypatch, render_check, _raise)
    status, detail = render_check.check_render_health("https://example.com/healthz")
    assert status == render_check.TIMEOUT
    assert detail["http_status"] is None


def test_4_invalid_json(monkeypatch):
    _patch_urlopen(monkeypatch, render_check,
                   lambda req, timeout=None: _FakeResponse(200, b"not-json{"))
    status, detail = render_check.check_render_health("https://example.com/healthz")
    assert status == render_check.INVALID_RESPONSE
    assert detail["http_status"] == 200


def test_5_unexpected_health_response(monkeypatch):
    _patch_urlopen(monkeypatch, render_check,
                   lambda req, timeout=None: _FakeResponse(200, b'{"status": "down"}'))
    status, detail = render_check.check_render_health("https://example.com/healthz")
    assert status == render_check.INVALID_RESPONSE


# ---- Supabase activity check ----

def test_6_missing_supabase_configuration():
    config, missing = supabase_check.load_config(env={})
    assert config is None
    assert set(missing) == {"SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_TABLE"}
    # main() with an empty env must report CONFIGURATION_MISSING (exit 2),
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
    assert supabase_check.CONFIGURATION_MISSING in buf.getvalue()


def test_7_successful_database_read(monkeypatch):
    _patch_urlopen(monkeypatch, supabase_check,
                   lambda req, timeout=None: _FakeResponse(200, b'[{"id": 1}]'))
    status, detail = supabase_check.check_supabase_activity(
        "https://xyz.supabase.co", "anon-key", "some_table")
    assert status == supabase_check.HEALTHY
    assert detail["http_status"] == 200
    assert detail["rows"] == 1


def test_8_failed_database_read(monkeypatch):
    """A reachable URL with a rejected query (401/RLS, 404/unknown table) is
    DATABASE_QUERY_FAILED — success must never be fabricated from liveness."""
    for code in (401, 404):
        def _raise(req, timeout=None, _code=code):
            raise urllib.error.HTTPError(req.full_url, _code, "error", {}, None)
        _patch_urlopen(monkeypatch, supabase_check, _raise)
        status, detail = supabase_check.check_supabase_activity(
            "https://xyz.supabase.co", "anon-key", "some_table")
        assert status == supabase_check.DATABASE_QUERY_FAILED
        assert detail["http_status"] == code
        assert detail["rows"] is None


def test_9_no_accidental_database_writes():
    """The activity script may only ever issue a bounded read-only GET."""
    src = open(os.path.join(SCRIPTS, "supabase_activity_check.py"), encoding="utf-8").read()
    assert 'method="GET"' in src
    verbs = ["POST", "PUT", "PATCH", "DELETE"]
    for verb in verbs:
        assert "method=\"" + verb + "\"" not in src, f"mutating request method: {verb}"
        assert "method='" + verb + "'" not in src, f"mutating request method: {verb}"
    for keyword in ("INSERT INTO", "UPDATE ", "DELETE FROM", "CREATE TABLE", "ALTER TABLE",
                    "DROP TABLE", "execute(", ".execute("):
        assert keyword not in src, f"write-like statement found: {keyword}"
    # The one live request is GET + limit=1.
    request = supabase_check.build_query_request(
        "https://xyz.supabase.co/", "some_table", "anon-key")
    assert request.get_method() == "GET"
    assert "limit=1" in request.full_url
    assert "select=" in request.full_url


def test_10_no_secrets_in_diagnostic_output(monkeypatch, capsys):
    """Neither success nor failure output may echo key material or row data."""
    secret_key = "eyJhbGciOiJIUzI1NiIsInRlc3Qtc2VjcmV0LWtleS1hYmMxMjM"
    _patch_urlopen(monkeypatch, supabase_check,
                   lambda req, timeout=None: _FakeResponse(200, b'[{"secret": "row-data"}]'))
    status, _ = supabase_check.check_supabase_activity(
        "https://xyz.supabase.co", secret_key, "some_table")
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

    def _raise(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, secret_key, {}, None)
    _patch_urlopen(monkeypatch, supabase_check, _raise)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = supabase_check.main([])
    assert code == 1
    failure_out = buf.getvalue()
    assert secret_key not in failure_out
    capsys.readouterr()  # keep pytest capture clean
