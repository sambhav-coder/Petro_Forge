"""Render health check for the PetroForge GitHub Actions monitor.

Lightweight, dependency-free (Python standard library only):

* HTTP GET against the deployed ``/healthz`` endpoint.
* Validates HTTP 200, valid JSON, and the expected ``{"status": "ok"}`` body.
* Logs an ISO-8601 UTC timestamp, HTTP status code and latency — never secrets
  (this check uses no credentials at all).
* Bounded retry: at most one retry (2 attempts total) for timeouts and 5xx;
  4xx and invalid payloads are final with no retry. No tight loops, no writes.

Outcome vocabulary: HEALTHY (fast 200+ok), SLOW_START (200+ok but slow,
typical Render free-tier cold start), TIMEOUT, HTTP_ERROR, INVALID_RESPONSE.
HEALTHY and SLOW_START both exit 0 (endpoint responded correctly); the label
keeps cold starts visible instead of confusing them with outages.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Tuple

# Outcome vocabulary shared with the workflow logs.
HEALTHY = "HEALTHY"
SLOW_START = "SLOW_START"
TIMEOUT = "TIMEOUT"
HTTP_ERROR = "HTTP_ERROR"
INVALID_RESPONSE = "INVALID_RESPONSE"

# Backwards-compatibility alias.
UNAVAILABLE = HTTP_ERROR

DEFAULT_URL = "https://petro-forge.onrender.com/healthz"
# Render free-tier cold starts take ~60 s (observed ~45 s on 2026-10-13), so the
# default total timeout must comfortably exceed that or every cold start would
# look like an outage. urllib exposes a single total timeout; that is what this
# value is. Keep it well under the workflow job timeout (5 min).
DEFAULT_TIMEOUT_S = 90.0
# Above this latency a valid 200+ok response is labelled SLOW_START (cold start)
# rather than HEALTHY. Still exit 0: the endpoint responded correctly.
SLOW_START_THRESHOLD_S = 15.0
MAX_ATTEMPTS = 2  # one initial try + one bounded retry for timeout/5xx only
RETRY_BACKOFF_S = 5.0


def _write_summary(lines: list) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    except OSError:
        pass


def _classify_success(latency_s: float) -> str:
    return SLOW_START if latency_s >= SLOW_START_THRESHOLD_S else HEALTHY


def check_render_health(url: str, timeout_s: float = DEFAULT_TIMEOUT_S) -> Tuple[str, dict]:
    """Perform a bounded health check. Returns ``(status, detail)``; never raises."""
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    started = time.monotonic()
    last_timeout_reason = "request timed out"

    for attempt in range(1, MAX_ATTEMPTS + 1):
        request = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                code = response.status
                raw = response.read()
        except urllib.error.HTTPError as exc:  # non-2xx from the server / Render
            latency_s = round(time.monotonic() - started, 3)
            # Retry 5xx once (transient/cold-start); 4xx is final.
            if 500 <= exc.code < 600 and attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_BACKOFF_S)
                continue
            return HTTP_ERROR, {
                "timestamp": timestamp,
                "http_status": exc.code,
                "latency_s": latency_s,
                "reason": "non-success HTTP status",
            }
        except TimeoutError:
            last_timeout_reason = "request timed out"
        except urllib.error.URLError as exc:  # DNS / refused / socket timeout etc.
            reason = getattr(exc.reason, "strerror", None) or str(exc.reason)
            lowered = reason.lower()
            if "timed out" in lowered:
                last_timeout_reason = "request timed out"
            else:
                latency_s = round(time.monotonic() - started, 3)
                return HTTP_ERROR, {
                    "timestamp": timestamp,
                    "http_status": None,
                    "latency_s": latency_s,
                    "reason": reason,
                }
        except (OSError, ValueError) as exc:  # connection reset, bad URL, ...
            latency_s = round(time.monotonic() - started, 3)
            return HTTP_ERROR, {
                "timestamp": timestamp,
                "http_status": None,
                "latency_s": latency_s,
                "reason": str(exc),
            }
        else:
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
            if code != 200 or not isinstance(body, dict) or body.get("status") != "ok":
                return INVALID_RESPONSE, {
                    "timestamp": timestamp,
                    "http_status": code,
                    "latency_s": latency_s,
                    "reason": "unexpected health payload (expected HTTP 200 JSON object with status 'ok')",
                }
            status = _classify_success(latency_s)
            return status, {
                "timestamp": timestamp,
                "http_status": code,
                "latency_s": latency_s,
                "problem_id": body.get("problem_id"),
                "version": body.get("version"),
            }
        if attempt < MAX_ATTEMPTS:
            # Only timeouts reach this retry point (other failures return).
            # Detect timeout vs immediate retry: sleep briefly then retry once.
            time.sleep(RETRY_BACKOFF_S)

    latency_s = round(time.monotonic() - started, 3)
    return TIMEOUT, {
        "timestamp": timestamp,
        "http_status": None,
        "latency_s": latency_s,
        "reason": last_timeout_reason,
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
    if status in (HEALTHY, SLOW_START):
        print(f"problem_id={detail.get('problem_id')} version={detail.get('version')}", flush=True)
        if status == SLOW_START:
            print("note=valid response but slow: likely Render cold start; "
                  "service responded within timeout", flush=True)
    else:
        print(f"reason={detail.get('reason')}", flush=True)
    _write_summary([
        "## Render health monitor",
        f"- status: `{status}`",
        f"- http_status: `{detail['http_status']}`",
        f"- latency_s: `{detail['latency_s']}`",
        f"- url: `{args.url}`",
    ])
    return 0 if status in (HEALTHY, SLOW_START) else 1


if __name__ == "__main__":
    sys.exit(main())
