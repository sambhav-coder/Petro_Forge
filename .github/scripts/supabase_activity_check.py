"""Supabase activity check for the PetroForge GitHub Actions monitor.

Dependency-free (Python standard library only). Performs exactly one minimal,
read-only query against the owner's Supabase project:

    HEAD {SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?select={PK_COLUMN}&limit=0

with the anonymous/publishable key as ``apikey`` + ``Bearer`` headers.

Why HEAD + limit=0:
* Requests NO record payload (no row bodies are transferred or printed).
* Avoids select-star (only the configured primary-key column is selected).
* A single bounded read; no INSERT/UPDATE/DELETE, no migrations, no writes.

Rules enforced by this script:

* Read-only: a single HTTP HEAD with ``limit=0``. No mutating methods.
* Secrets are never printed: logs contain timestamp, status, HTTP status,
  elapsed time, table/column names and row-count zero only.
* Success (HEALTHY) is reported ONLY when the database query itself returns
  HTTP 2xx to the HEAD request. A reachable URL with a failing query is
  HTTP_ERROR, never HEALTHY.
* Missing configuration is CONFIG_MISSING (exit 2), never success.
* QUERY_UNVERIFIED is returned when the HTTP layer succeeds but the response
  does not carry evidence the query reached the database (no Content-Range
  header on a 2xx). This avoids false-green HEALTHY claims.
* A successful HTTP request is NOT proof Supabase will not pause the project:
  pausing follows Supabase's own activity assessment; only paid plans are
  exempt. See README monitoring section.

Configuration (GitHub Actions secrets/variables, see the workflow file):

* ``SUPABASE_URL`` — e.g. ``https://xyzcompany.supabase.co`` (secret)
* ``SUPABASE_ANON_KEY`` — publishable/anon key, read-only (secret; NEVER the
  service-role key for this check)
* ``SUPABASE_TABLE`` — an existing table the anon key may SELECT (secret)
* ``SUPABASE_PK_COLUMN`` — primary-key (or any readable) column to select
  (repository variable, default ``id``). The PetroForge backend in this repo
  has NO Supabase integration (in-memory storage only), so no default table
  exists: the owner must supply a real table + readable column. Until the
  secrets/variable exist, every run reports CONFIGURATION_MISSING.

Exit codes: 0 = HEALTHY, 1 = HTTP_ERROR/TIMEOUT/QUERY_UNVERIFIED, 2 = missing config.
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Tuple

HEALTHY = "HEALTHY"
CONFIG_MISSING = "CONFIG_MISSING"
HTTP_ERROR = "HTTP_ERROR"
TIMEOUT = "TIMEOUT"
QUERY_UNVERIFIED = "QUERY_UNVERIFIED"

# Backwards-compatibility aliases (older vocabulary used by previous runs).
CONFIGURATION_MISSING = CONFIG_MISSING
DATABASE_QUERY_FAILED = HTTP_ERROR
UNAVAILABLE = HTTP_ERROR
INVALID_RESPONSE = QUERY_UNVERIFIED

DEFAULT_TIMEOUT_S = 30.0
DEFAULT_PK_COLUMN = "id"
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


def _write_summary(lines: list) -> None:
    """Append a short job summary via GitHub Actions step-summary if available."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    except OSError:
        pass


def build_query_request(base_url: str, table: str, anon_key: str,
                        select_column: str = DEFAULT_PK_COLUMN,
                        timeout_s: float = DEFAULT_TIMEOUT_S) -> urllib.request.Request:
    """Build the single read-only REST request (HEAD, limit=0, no payload)."""
    encoded_table = urllib.parse.quote(table, safe="")
    encoded_col = urllib.parse.quote(select_column, safe="")
    url = f"{base_url.rstrip('/')}/rest/v1/{encoded_table}?select={encoded_col}&limit=0"
    return urllib.request.Request(
        url,
        method="HEAD",
        headers={
            "apikey": anon_key,
            "Authorization": f"Bearer {anon_key}",
            "Accept": "application/json",
        },
    )


def check_supabase_activity(base_url: str, anon_key: str, table: str,
                            select_column: str = DEFAULT_PK_COLUMN,
                            timeout_s: float = DEFAULT_TIMEOUT_S) -> Tuple[str, dict]:
    """Run the read-only HEAD query. Returns ``(status, detail)``; never raises."""
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    started = time.monotonic()
    last_error: str | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        request = build_query_request(base_url, table, anon_key, select_column, timeout_s)
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                code = response.status
                # HEAD responses carry no body by definition; evidence the
                # query reached PostgREST is the Content-Range header.
                getheader = getattr(response, "getheader", None)
                content_range = getheader("Content-Range") if callable(getheader) else None
                headers = getattr(response, "headers", None)
                if content_range is None and headers is not None:
                    try:
                        content_range = headers.get("Content-Range")
                    except Exception:
                        content_range = None
        except urllib.error.HTTPError as exc:
            # The database answered but the query failed (401 bad key / RLS
            # denial, 404 unknown table/column, ...). HTTP errors are final —
            # no retry, since retrying a rejected query is pointless.
            latency_s = round(time.monotonic() - started, 3)
            return HTTP_ERROR, {
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
                return HTTP_ERROR, {
                    "timestamp": timestamp,
                    "http_status": None,
                    "latency_s": latency_s,
                    "rows": None,
                    "reason": _redact(reason),
                }
        except (OSError, ValueError) as exc:
            latency_s = round(time.monotonic() - started, 3)
            return HTTP_ERROR, {
                "timestamp": timestamp,
                "http_status": None,
                "latency_s": latency_s,
                "rows": None,
                "reason": _redact(exc),
            }
        else:
            latency_s = round(time.monotonic() - started, 3)
            if 200 <= code < 300:
                if content_range is not None:
                    return HEALTHY, {
                        "timestamp": timestamp,
                        "http_status": code,
                        "latency_s": latency_s,
                        "rows": 0,
                        "reason": None,
                    }
                return QUERY_UNVERIFIED, {
                    "timestamp": timestamp,
                    "http_status": code,
                    "latency_s": latency_s,
                    "rows": 0,
                    "reason": "2xx without Content-Range: database reach unverified",
                }
            return HTTP_ERROR, {
                "timestamp": timestamp,
                "http_status": code,
                "latency_s": latency_s,
                "rows": None,
                "reason": f"unexpected HTTP status {code}",
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
    select_col = (source.get("SUPABASE_PK_COLUMN") or DEFAULT_PK_COLUMN).strip() or DEFAULT_PK_COLUMN
    return {
        "url": (source.get("SUPABASE_URL") or "").strip(),
        "anon_key": (source.get("SUPABASE_ANON_KEY") or "").strip(),
        "table": (source.get("SUPABASE_TABLE") or "").strip(),
        "select_column": select_col,
    }, []


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one read-only Supabase HEAD activity query.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S,
                        help="Per-request timeout in seconds (default: 30).")
    parser.add_argument("--select-column", default=None,
                        help="Readable column to select (default: $SUPABASE_PK_COLUMN or 'id').")
    args = parser.parse_args(argv)

    config, missing = load_config()
    if config is None:
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        print(f"[{timestamp}] status={CONFIG_MISSING} "
              f"missing={','.join(missing)}", flush=True)
        print("Owner action: set repository secrets SUPABASE_URL, SUPABASE_ANON_KEY "
              "and SUPABASE_TABLE (an existing table readable by the anon key). "
              "No values are printed here. See README monitoring section.", flush=True)
        _write_summary([
            "## Supabase activity monitor",
            f"- status: `{CONFIG_MISSING}`",
            f"- missing: `{','.join(missing)}`",
            "- Set SUPABASE_URL / SUPABASE_ANON_KEY / SUPABASE_TABLE secrets.",
        ])
        return 2

    select_column = (args.select_column or config["select_column"]).strip() or DEFAULT_PK_COLUMN
    status, detail = check_supabase_activity(
        config["url"], config["anon_key"], config["table"], select_column, args.timeout)
    # Log table/column + zero-row intent only; the key and any payload are NEVER printed
    # (HEAD responses carry no body by design).
    print(f"[{detail['timestamp']}] status={status} "
          f"http_status={detail['http_status']} latency_s={detail['latency_s']} "
          f"table={config['table']} select={select_column} rows={detail['rows']}", flush=True)
    if detail.get("reason"):
        print(f"reason={detail['reason']}", flush=True)
    if status != HEALTHY:
        print("Note: a successful HTTP request does not guarantee Supabase will "
              "not pause the project; pausing follows Supabase's own activity "
              "assessment.", flush=True)
    _write_summary([
        "## Supabase activity monitor",
        f"- status: `{status}`",
        f"- http_status: `{detail['http_status']}`",
        f"- latency_s: `{detail['latency_s']}`",
        f"- table: `{config['table']}`",
    ])
    return 0 if status == HEALTHY else 1


if __name__ == "__main__":
    sys.exit(main())
