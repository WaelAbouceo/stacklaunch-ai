"""Data-residency + egress control — the sovereign-stack guarantees.

Two responsibilities:

  1. SSRF / egress guard: the scanner fetches user-supplied URLs, so without a
     guard it could be turned into a probe of internal services or cloud-metadata
     endpoints (169.254.169.254). `assert_safe_target` resolves the host and
     rejects private / loopback / link-local / reserved addresses unless private
     scanning is explicitly enabled for dev.

  2. Posture manifest: a single, inspectable statement of where data lives and
     where (if anywhere) traffic can egress — surfaced at /api/sovereignty so the
     sovereign stance is provable, not just claimed.

This module is intentionally dependency-light and import-safe; `posture()` imports
peer modules lazily to avoid cycles.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from core import config


class EgressBlocked(Exception):
    """Raised when an outbound target violates the egress / residency policy."""


def host_of(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url if "//" in url else f"//{url}")
    return (parsed.hostname or "").lower() or None


# --- LLM host classification ---------------------------------------------

def is_external_llm(host: str | None) -> bool:
    """True if the host is a known non-sovereign public-cloud inference endpoint."""
    if not host:
        return False
    h = host.lower()
    return any(h == ext or h.endswith("." + ext) for ext in config.EXTERNAL_LLM_HOSTS)


def _is_local_host(host: str | None) -> bool:
    if not host:
        return False
    if host in ("localhost",):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def classify_residency(host: str | None) -> dict:
    """Classify an LLM endpoint for the posture manifest."""
    if not host:
        return {"code": "none", "label": "No LLM configured (heuristic fallback)"}
    if is_external_llm(host):
        return {"code": "external", "label": "External public-cloud endpoint"}
    if _is_local_host(host):
        return {"code": "self_hosted", "label": "Self-hosted / on-prem (local)"}
    return {"code": "sovereign", "label": f"Sovereign region ({config.DATA_REGION})"}


# --- SSRF / egress guard --------------------------------------------------

def _resolved_ips(host: str) -> list[ipaddress._BaseAddress]:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise EgressBlocked(f"Could not resolve host '{host}'.") from exc
    ips: list[ipaddress._BaseAddress] = []
    for info in infos:
        addr = info[4][0]
        try:
            ips.append(ipaddress.ip_address(addr.split("%")[0]))
        except ValueError:
            continue
    return ips


def _is_blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local  # includes 169.254.169.254 cloud metadata
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def is_safe_target(url: str) -> bool:
    try:
        assert_safe_target(url)
        return True
    except EgressBlocked:
        return False


def assert_safe_target(url: str) -> None:
    """Raise EgressBlocked if `url` is not a safe public http(s) target.

    Blocks non-http(s) schemes and any host that resolves to a private, loopback,
    link-local (cloud metadata), reserved, or multicast address — unless
    ALLOW_PRIVATE_SCAN is set for local development.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise EgressBlocked(f"Scheme '{parsed.scheme or '?'}' is not allowed; use http(s).")
    host = (parsed.hostname or "").lower()
    if not host:
        raise EgressBlocked("URL has no host.")
    if config.ALLOW_PRIVATE_SCAN:
        return
    for ip in _resolved_ips(host):
        if _is_blocked_ip(ip):
            raise EgressBlocked(
                f"Target '{host}' resolves to a non-public address ({ip}); blocked "
                f"by the sovereign egress policy (set ALLOW_PRIVATE_SCAN=1 for dev)."
            )


# --- Startup validation + posture report ---------------------------------

def validate_startup() -> list[str]:
    """Return human-readable posture warnings. In strict mode, raise on a
    non-sovereign LLM endpoint that hasn't been explicitly allowed."""
    from core import llm

    warnings: list[str] = []
    info = llm.provider_info()
    host = info.get("host")
    if is_external_llm(host) and not config.ALLOW_EXTERNAL_LLM:
        msg = (
            f"LLM endpoint '{host}' is a non-sovereign public cloud and "
            f"ALLOW_EXTERNAL_LLM is not set."
        )
        if config.SOVEREIGN_STRICT:
            raise EgressBlocked(f"Strict sovereignty: {msg}")
        warnings.append(msg)
    if config.ALLOW_PRIVATE_SCAN:
        warnings.append("ALLOW_PRIVATE_SCAN is on — scanner SSRF guard is relaxed (dev only).")
    return warnings


def posture() -> dict:
    """A structured, inspectable statement of the sovereign data/egress stance."""
    from core import llm
    from data import search

    info = llm.provider_info()
    host = info.get("host")
    return {
        "dataRegion": config.DATA_REGION,
        "strict": config.SOVEREIGN_STRICT,
        "llm": {
            "provider": info.get("provider"),
            "model": info.get("model"),
            "host": host,
            "residency": classify_residency(host),
        },
        "search": {
            "engine": "SearXNG (self-hosted)",
            "host": host_of(search.SEARXNG_URL),
        },
        "egress": {
            "scanSsrfGuard": True,
            "allowPrivateScan": config.ALLOW_PRIVATE_SCAN,
            "externalLlmAllowed": config.ALLOW_EXTERNAL_LLM,
            "knownExternalHosts": sorted(config.EXTERNAL_LLM_HOSTS),
        },
        "dataAtRest": {
            "store": "SQLite (local)",
            "appDb": config.APP_DB_PATH,
            "auditDb": config.AUDIT_DB_PATH,
        },
        "controls": {
            "auditHashChained": True,
            "auditHmacSigned": True,
            "piiRedaction": True,
            "promptInjectionDefense": True,
            "rbac": True,
            "requireAuth": config.REQUIRE_AUTH,
        },
    }
