"""Deployment configuration (production hardening).

CORS origins are explicit — never a wildcard in production. The baked-in
defaults cover the production frontend plus local development; the
PETROFORGE_CORS_ORIGINS environment variable (comma-separated) can extend
or replace them. Invalid configuration fails fast at startup with a clear
message instead of silently opening or closing the API.

No secrets live here: origins and URLs are public configuration.
"""

import os
import re
from typing import List, Optional

PRODUCTION_FRONTEND_ORIGIN = "https://petro-forge.vercel.app"

LOCAL_DEV_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)

DEFAULT_ORIGINS: List[str] = [PRODUCTION_FRONTEND_ORIGIN, *LOCAL_DEV_ORIGINS]

CORS_ENV_VAR = "PETROFORGE_CORS_ORIGINS"

_ORIGIN_RE = re.compile(r"^https?://[A-Za-z0-9._-]+(?::\d+)?$")


def _validate_origin(value: str) -> str:
    origin = value.strip().rstrip("/")
    if not _ORIGIN_RE.match(origin):
        raise ValueError(
            f"invalid CORS origin {value!r}: expected scheme://host[:port] "
            "with no path, query or wildcard"
        )
    return origin


def resolve_cors_origins(raw: Optional[str] = None) -> List[str]:
    """Resolve the effective CORS origin allow-list.

    raw=None (env unset) -> baked-in defaults (production + local dev).
    raw set -> comma-separated override; must yield at least one valid
    origin or a ValueError is raised. Duplicates removed, order kept.
    A literal "*" is always rejected.
    """
    if raw is None:
        raw = os.environ.get(CORS_ENV_VAR)
    if raw is None or not raw.strip():
        return list(DEFAULT_ORIGINS)
    if "*" in (part.strip() for part in raw.split(",")):
        raise ValueError("wildcard CORS origin '*' is not allowed in production")
    seen: List[str] = []
    for part in raw.split(","):
        if not part.strip():
            continue
        origin = _validate_origin(part)
        if origin not in seen:
            seen.append(origin)
    if not seen:
        raise ValueError(
            f"{CORS_ENV_VAR} is set but contains no valid origins; "
            "set at least one scheme://host[:port] origin or unset it "
            "to use the defaults"
        )
    return seen
