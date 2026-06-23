"""Central configuration + shared time source.

Single place that reads environment/config so settings aren't scattered across
modules, and a single `now_utc()` time source so "this week / recent" logic never
rots (previously the reference date was hardcoded to 2026-06-21 in three files).

Also makes imports CWD-independent: importing this module inserts the backend root
(the parent of this `core/` package) onto sys.path, so the layered packages resolve
regardless of the working directory.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

# --- CWD-safe imports -----------------------------------------------------
# config.py lives at backend/core/config.py -> the backend root is two levels up.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def _path(env: str, default_name: str) -> str:
    return os.getenv(env, os.path.join(_BACKEND_DIR, default_name))


# --- Time -----------------------------------------------------------------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_ts() -> float:
    return now_utc().timestamp()


def week_ago_ts() -> float:
    return now_ts() - 7 * 24 * 60 * 60


# --- Persistence ----------------------------------------------------------
AUDIT_DB_PATH = _path("AUDIT_DB_PATH", "audit.db")
APP_DB_PATH = _path("APP_DB_PATH", "app.db")

# --- Security -------------------------------------------------------------
# When true, mutating/data endpoints require a valid API key (X-API-Key).
# Defaults to false so the existing demo/frontend keeps working out of the box;
# set REQUIRE_AUTH=1 to enforce.
REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "").strip().lower() in ("1", "true", "yes")

# CORS: comma-separated origins. "*" allowed only when auth is NOT required.
_origins_raw = os.getenv("ALLOWED_ORIGINS", "").strip()
if _origins_raw:
    ALLOWED_ORIGINS = [o.strip() for o in _origins_raw.split(",") if o.strip()]
else:
    ALLOWED_ORIGINS = ["*"] if not REQUIRE_AUTH else [
        "http://localhost:5173", "http://localhost:5174",
    ]

# Secret used to HMAC-sign audit rows (non-repudiation). Generated per-process if
# unset; set AUDIT_HMAC_SECRET in production so signatures survive restarts.
AUDIT_HMAC_SECRET = os.getenv("AUDIT_HMAC_SECRET", "").strip() or os.urandom(16).hex()

# --- Rate limiting --------------------------------------------------------
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "60"))

# --- Sovereignty / data residency ----------------------------------------
def _flag(name: str, default: str = "") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")


# Declared data-residency region for the posture manifest (informational).
DATA_REGION = os.getenv("DATA_REGION", "EG").strip() or "EG"

# Strict mode: refuse to operate with a non-sovereign LLM endpoint and forbid any
# egress to non-allowlisted hosts. Off by default so the demo runs out of the box.
SOVEREIGN_STRICT = _flag("SOVEREIGN_STRICT")

# Explicitly permit a non-sovereign (public-cloud) LLM endpoint. Even off, the app
# still runs in non-strict mode but flags the posture as "external".
ALLOW_EXTERNAL_LLM = _flag("ALLOW_EXTERNAL_LLM")

# Allow the scanner to reach private/loopback hosts (dev only). Off by default so
# scans can never be turned into SSRF against internal services / cloud metadata.
ALLOW_PRIVATE_SCAN = _flag("ALLOW_PRIVATE_SCAN")

# Hostnames considered non-sovereign public-cloud inference endpoints. Used to
# classify the active provider and to gate strict mode.
EXTERNAL_LLM_HOSTS = {
    h.strip().lower()
    for h in os.getenv(
        "EXTERNAL_LLM_HOSTS",
        "api.openai.com,api.anthropic.com,generativelanguage.googleapis.com,"
        "api.mistral.ai,api.cohere.ai,api.groq.com,api.together.xyz,"
        "api.deepseek.com,openrouter.ai",
    ).split(",")
    if h.strip()
}

# --- LLM telemetry pricing (USD per 1K tokens; rough, for cost estimates) ---
PRICE_PER_1K_PROMPT = float(os.getenv("PRICE_PER_1K_PROMPT", "0.00015"))
PRICE_PER_1K_COMPLETION = float(os.getenv("PRICE_PER_1K_COMPLETION", "0.0006"))
