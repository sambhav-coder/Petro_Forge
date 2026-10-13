"""Supabase activity check for the PetroForge GitHub Actions monitor.

Dependency-free (Python standard library only). Performs exactly one genuine,
harmless, read-only query against the owner's Supabase project:

    GET {SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?select=*&limit=1

with the anonymous/publishable key as ``apikey`` + ``Bearer`` headers.

Rules enforced by this script:

* Read-only: a single HTTP GET with ``limit=1``. No INSERT/UPDATE/DELETE, no
  migrations, no table creation, no writes of any kind (also asserted by the
  test-suite, which greps this file for mutating methods).
* Secrets are never printed: on success only the row count is logged; on
  failure only the HTTP status and a redacted reason are logged.
* Success is reported ONLY when the database query itself returns HTTP 200
  with a valid JSON payload. A reachable URL with a failing query is
  DATABASE_QUERY_FAILED, never HEALTHY.
* Missing configuration (URL / anon key / table name) is reported as
  CONFIGURATION_MISSING with the exact owner action required — never as
  success, never fabricated.

Configuration (GitHub Actions secrets, see the workflow file):

* ``SUPABASE_URL`` — e.g. ``https://xyzcompany.supabase.co`` (no trailing slash)
* ``SUPABASE_ANON_KEY`` — publishable/anon key (read-only). Never the
  service-role key for this keep-alive query.
* ``SUPABASE_TABLE`` — an existing table the anon key is allowed to SELECT
  (e.g. via a permissive SELECT RLS policy). The PetroForge backend in this
  repository currently has NO Supabase integration (in-memory storage only),
  so there is no default: the owner must supply a real table name. Until the
  three secrets exist, every run reports CONFIGURATION_MISSING.

Exit codes: 0 = HEALTHY, 1 = query/timeout/response failure, 2 = missing config.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Tuple

HEALTHY = "HEALTHY"
UNAVAILABLE = "UNAVAILABLE"
TIMEOUT = "TIMEOUT"
INVALID_RESPONSE = "INVALID_RESPONSE"
CONFIGURATION_MISSING = "CONFIGURATION_MISSING"
DATABASE_QUERY_FAILED = "DATABASE_QUERY_FAILED"

DEFAULT_TIMEOUT_S = 30.0
MAX_ATTEMPTS = 2  # one initial try + one bounded retry (never a tight loop)
RETRY_BACKOFF_S = 5.0

REQUIRED_VARS = ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_TABLE")


def _redact(reason: str) -> str:
    """Defensive scrub so a proxied error body can never leak a key fragment."""
    text = str(reason)
    for var in ("SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_DB_PASSWORD"):
        value = os.environ.get(var)
        if value and value in text:
            text = text.replace(value, "***redacted***")
    return text


def build_query_request(base_url: str, table: str, anon_key: str,
                        timeout_s: float = DEFAULT_TIMEOUT_S) -> urllib.request.Request:
    """Build the single read-only REST request (GET, limit=1)."""
    encoded_table = urllib.parse.quote(table, safe="")
    url = f"{base_url.rstrip('/')}/rest/v1/{encoded_table}?select=*&limit=1"
    return urllib.request.Request(
        url,
        method="GET",
        headers={
            "apikey": anon_key,
            "Authorization": f"Bearer {anon_key}",
            "Accept": "application/json",
        },
    )


def check_supabase_activity(base_url: str, anon_key: str, table: str,
                            timeout_s: float = DEFAULT_TIMEOUT_S) -> Tuple[str, dict]:
    """Run the read-only query. Returns ``(status, detail)``; never raises."""
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    started = time.monotonic()
    last_error: str | None = None
    last_code: int | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        request = build_query_request(base_url, table, anon_key, timeout_s)
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                raw = response.read()
                last_code = response.status
        except urllib.error.HTTPError as exc:
            # The database answered but the query failed (401 bad key / RLS
            # denial, 404 unknown table, ...). Never a tight loop: HTTP errors
            # are final — no retry, since retrying a rejected query is pointless.
            latency_s = round(time.monotonic() - started, 3)
            return DATABASE_QUERY_FAILED, {
                "timestamp": timestamp,
                "http_status": exc.code,
                "latency_s": latency_s,
                "rows": None,
                "reason": _redact(f"database query failed with HTTP {exc.code}"),
            }
        except TimeoutError:
            last_error = "request timed out"
        except urllib.error.URLError as exc:
            reason = getattr(exc.reason, "strerror", None) or str(exc.reason)
            if "timed out" in reason.lower():
                last_error = "request timed out"
            else:
                latency_s = round(time.monotonic() - started, 3)
                return UNAVAILABLE, {
                    "timestamp": timestamp,
                    "http_status": None,
                    "latency_s": latency_s,
                    "rows": None,
                    "reason": _redact(reason),
                }
        except (OSError, ValueError) as exc:
            latency_s = round(time.monotonic() - started, 3)
            return UNAVAILABLE, {
                "timestamp": timestamp,
                "http_status": None,
                "latency_s": latency_s,
                "rows": None,
                "reason": _redact(exc),
            }
        else:
            latency_s = round(time.monotonic() - started, 3)
            try:
                body: Any = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return INVALID_RESPONSE, {
                    "timestamp": timestamp,
                    "http_status": last_code,
                    "latency_s": latency_s,
                    "rows": None,
                    "reason": "response is not valid JSON",
                }
            if not isinstance(body, list):
                return INVALID_RESPONSE, {
                    "timestamp": timestamp,
                    "http_status": last_code,
                    "latency_s": latency_s,
                    "rows": None,
                    "reason": "unexpected payload (expected a JSON array of rows)",
                }
            # Genuine database activity: the query itself succeeded.
            return HEALTHY, {
                "timestamp": timestamp,
                "http_status": last_code,
                "latency_s": latency_s,
                "rows": len(body),
                "reason": None,
            }
        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_BACKOFF_S)

    latency_s = round(time.monotonic() - started, 3)
    return TIMEOUT, {
        "timestamp": timestamp,
        "http_status": None,
        "latency_s": latency_s,
        "rows": None,
        "reason": _redact(last_error or "request timed out"),
    }


def load_config(env: dict | None = None) -> Tuple[dict | None, list]:
    """Read required config from the environment. Returns (config, missing)."""
    source = env if env is not None else os.environ
    missing = [var for var in REQUIRED_VARS if not (source.get(var) or "").strip()]
    if missing:
        return None, missing
    return {
        "url": (source.get("SUPABASE_URL") or "").strip(),
        "anon_key": (source.get("SUPABASE_ANON_KEY") or "").strip(),
        "table": (source.get("SUPABASE_TABLE") or "").strip(),
    }, []


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one read-only Supabase activity query.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S,
                        help="Per-request timeout in seconds (default: 30).")
    args = parser.parse_args(argv)

    config, missing = load_config()
    if config is None:
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        print(f"[{timestamp}] status={CONFIGURATION_MISSING} "
              f"missing={','.join(missing)}", flush=True)
        print("Owner action: set repository secrets SUPABASE_URL, SUPABASE_ANON_KEY "
              "and SUPABASE_TABLE (an existing table readable by the anon key). "
              "No values are printed here. See README monitoring section.", flush=True)
        return 2

    status, detail = check_supabase_activity(
        config["url"], config["anon_key"], config["table"], args.timeout)
    # Log table name + row count only; the URL host is public config but the key
    # and any row contents are NEVER printed.
    print(f"[{detail['timestamp']}] status={status} "
          f"http_status={detail['http_status']} latency_s={detail['latency_s']} "
          f"table={config['table']} rows={detail['rows']}", flush=True)
    if detail.get("reason"):
        print(f"reason={detail['reason']}", flush=True)
    return 0 if status == HEALTHY else 1


if __name__ == "__main__":
    sys.exit(main())
