"""Render health check for the PetroForge GitHub Actions monitor.

Lightweight, dependency-free (Python standard library only):

* One real HTTP GET against the deployed ``/healthz`` endpoint.
* Validates HTTP 200, valid JSON, and the expected ``{"status": "ok"}`` body.
* Logs an ISO-8601 UTC timestamp, HTTP status code and latency — never secrets
  (this check uses no credentials at all).
* Single attempt only: no tight retry loop, no expensive API calls, no writes.

Exit codes: 0 = HEALTHY, 1 = any failure (UNAVAILABLE / TIMEOUT /
INVALID_RESPONSE). A slow-but-200 response (Render free-tier cold start,
typically ~60 s) is still HEALTHY; latency is logged so cold starts stay
visible instead of being confused with permanent failures.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Tuple

# Outcome vocabulary shared with the workflow logs.
HEALTHY = "HEALTHY"
UNAVAILABLE = "UNAVAILABLE"
TIMEOUT = "TIMEOUT"
INVALID_RESPONSE = "INVALID_RESPONSE"

DEFAULT_URL = "https://petro-forge.onrender.com/healthz"
# Render free-tier cold starts take ~60 s (observed ~45 s on 2026-10-13), so the
# default total timeout must comfortably exceed that or every cold start would
# look like an outage. urllib exposes a single total timeout; that is what this
# value is. Keep it well under the workflow job timeout (5 min).
DEFAULT_TIMEOUT_S = 90.0


def check_render_health(url: str, timeout_s: float = DEFAULT_TIMEOUT_S) -> Tuple[str, dict]:
    """Perform one health check. Returns ``(status, detail)``; never raises."""
    started = time.monotonic()
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            code = response.status
            raw = response.read()
    except urllib.error.HTTPError as exc:  # non-2xx from the server / Render
        latency_s = round(time.monotonic() - started, 3)
        return UNAVAILABLE, {
            "timestamp": timestamp,
            "http_status": exc.code,
            "latency_s": latency_s,
            "reason": "non-success HTTP status",
        }
    except TimeoutError:
        latency_s = round(time.monotonic() - started, 3)
        return TIMEOUT, {
            "timestamp": timestamp,
            "http_status": None,
            "latency_s": latency_s,
            "reason": "request timed out",
        }
    except urllib.error.URLError as exc:  # DNS / refused / socket timeout etc.
        latency_s = round(time.monotonic() - started, 3)
        reason = getattr(exc.reason, "strerror", None) or str(exc.reason)
        lowered = reason.lower()
        status = TIMEOUT if "timed out" in lowered else UNAVAILABLE
        return status, {
            "timestamp": timestamp,
            "http_status": None,
            "latency_s": latency_s,
            "reason": reason,
        }
    except (OSError, ValueError) as exc:  # connection reset, bad URL, ...
        latency_s = round(time.monotonic() - started, 3)
        return UNAVAILABLE, {
            "timestamp": timestamp,
            "http_status": None,
            "latency_s": latency_s,
            "reason": str(exc),
        }

    latency_s = round(time.monotonic() - started, 3)
    try:
        body: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return INVALID_RESPONSE, {
            "timestamp": timestamp,
            "http_status": code,
            "latency_s": latency_s,
            "reason": "response is not valid JSON",
        }
    if not isinstance(body, dict) or body.get("status") != "ok":
        return INVALID_RESPONSE, {
            "timestamp": timestamp,
            "http_status": code,
            "latency_s": latency_s,
            "reason": "unexpected health payload (expected JSON object with status 'ok')",
        }
    return HEALTHY, {
        "timestamp": timestamp,
        "http_status": code,
        "latency_s": latency_s,
        "problem_id": body.get("problem_id"),
        "version": body.get("version"),
    }


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the PetroForge Render /healthz endpoint.")
    parser.add_argument("--url", default=DEFAULT_URL, help="Full /healthz URL (default: deployed backend).")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S,
                        help="Total request timeout in seconds (default: 90).")
    args = parser.parse_args(argv)

    status, detail = check_render_health(args.url, args.timeout)
    # One compact log line per run: timestamp, outcome, code, latency. No secrets
    # exist in this check, and nothing sensitive is ever printed.
    print(f"[{detail['timestamp']}] status={status} "
          f"http_status={detail['http_status']} latency_s={detail['latency_s']} "
          f"url={args.url}", flush=True)
    if status == HEALTHY:
        print(f"problem_id={detail.get('problem_id')} version={detail.get('version')}", flush=True)
    else:
        print(f"reason={detail.get('reason')}", flush=True)
    return 0 if status == HEALTHY else 1


if __name__ == "__main__":
    sys.exit(main())
