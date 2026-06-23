"""Authentication, API-key management, and rate limiting.

Replaces the cosmetic `generate_api_key` hash with real, revocable API keys whose
SHA-256 hashes are stored in SQLite (the plaintext key is shown exactly once on
creation). A FastAPI dependency resolves the caller into a `Principal` carrying its
role and expanded permission set, which RBAC then enforces.

Backward compatible: when `config.REQUIRE_AUTH` is false (the default), callers
without a key are treated as the Owner role so the existing frontend keeps working.
Set REQUIRE_AUTH=1 to require `X-API-Key` on protected endpoints.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass, field

from core import config
from governance import rbac

_db_path = config.APP_DB_PATH
_conn: sqlite3.Connection | None = None
_lock = threading.Lock()

KEY_PREFIX = "sk-sl-"

# Extra columns added for the enterprise org model. Legacy role-only keys simply
# leave these NULL and resolve to a full-access (system / restricted) principal so
# existing behaviour is preserved.
_EXTRA_COLUMNS = {
    "clearance": "TEXT",
    "admin_tier": "TEXT",
    "department": "TEXT",
    "grp": "TEXT",
    "permissions": "TEXT",
}


@dataclass
class Principal:
    role: str
    permissions: set[str]
    label: str = "anonymous"
    authenticated: bool = False
    # --- Enterprise org scope ---
    clearance: str = "restricted"
    admin_tier: str | None = None
    department: str | None = None
    group: str | None = None


def configure(path: str) -> None:
    """Repoint the key DB (for tests)."""
    global _conn, _db_path
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = None
        _db_path = path


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(_db_path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                key_hash   TEXT NOT NULL UNIQUE,
                label      TEXT NOT NULL,
                role       TEXT NOT NULL,
                created_at REAL NOT NULL,
                active     INTEGER NOT NULL DEFAULT 1,
                clearance  TEXT,
                admin_tier TEXT,
                department TEXT,
                grp        TEXT,
                permissions TEXT
            )
            """
        )
        # Migrate older DBs that predate the org columns.
        existing = {r["name"] for r in _conn.execute("PRAGMA table_info(api_keys)")}
        for col, decl in _EXTRA_COLUMNS.items():
            if col not in existing:
                _conn.execute(f"ALTER TABLE api_keys ADD COLUMN {col} {decl}")
        _conn.commit()
    return _conn


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def create_key(
    label: str,
    role: str,
    *,
    clearance: str | None = None,
    admin_tier: str | None = None,
    department: str | None = None,
    group: str | None = None,
    permissions: set[str] | None = None,
) -> dict:
    """Create an API key. Returns the plaintext key ONCE (never stored).

    Two modes:
      * Legacy role key — pass a ``role`` registered in rbac.ROLE_PERMISSIONS and
        leave the org fields unset; permissions are derived from the role.
      * Seat key (enterprise org) — pass an explicit ``permissions`` set plus the
        org scope (clearance / admin_tier / department / group); ``role`` is then a
        free-form seat label and is NOT validated against ROLE_PERMISSIONS.
    """
    seat_mode = permissions is not None
    if not seat_mode and role not in rbac.ROLE_PERMISSIONS:
        raise ValueError(f"Unknown role '{role}'. Valid: {sorted(rbac.ROLE_PERMISSIONS)}")
    perms = set(permissions) if seat_mode else rbac.permissions_for(role)
    key = KEY_PREFIX + secrets.token_hex(16)
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT INTO api_keys "
            "(key_hash, label, role, created_at, active, clearance, admin_tier, department, grp, permissions) "
            "VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?)",
            (
                _hash_key(key), label, role, time.time(),
                clearance, admin_tier, department, group, json.dumps(sorted(perms)),
            ),
        )
        conn.commit()
    return {"apiKey": key, "label": label, "role": role}


def list_keys() -> list[dict]:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT id, label, role, created_at, active FROM api_keys ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def revoke_key(key_id: int) -> bool:
    with _lock:
        conn = _connect()
        cur = conn.execute("UPDATE api_keys SET active = 0 WHERE id = ?", (key_id,))
        conn.commit()
        return cur.rowcount > 0


def resolve(key: str | None) -> Principal | None:
    """Resolve an API key to a Principal, or None if invalid/missing."""
    if not key:
        return None
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT label, role, clearance, admin_tier, department, grp, permissions "
            "FROM api_keys WHERE key_hash = ? AND active = 1",
            (_hash_key(key),),
        ).fetchone()
    if not row:
        return None
    role = row["role"]
    # Seat keys store their expanded permission set + scope; legacy role keys fall
    # back to the role's permissions and a full-access (system / restricted) scope.
    if row["permissions"]:
        perms = set(json.loads(row["permissions"]))
    else:
        perms = rbac.permissions_for(role)
    return Principal(
        role=role,
        permissions=perms,
        label=row["label"],
        authenticated=True,
        clearance=row["clearance"] or "restricted",
        admin_tier=row["admin_tier"],
        department=row["department"],
        group=row["grp"],
    )


def anonymous_principal() -> Principal:
    """Principal used when auth is disabled: full access for the demo/frontend."""
    return Principal(
        role=rbac.DEFAULT_ROLE,
        permissions=rbac.permissions_for(rbac.DEFAULT_ROLE),
        label="anonymous",
        authenticated=False,
        clearance="restricted",
        admin_tier="system",
        department=None,
        group=None,
    )


# --- Rate limiting (in-memory sliding window) -----------------------------

_buckets: dict[str, list[float]] = {}
_rl_lock = threading.Lock()


def check_rate_limit(identity: str, limit_per_min: int | None = None) -> bool:
    """Return True if the call is allowed; False if the per-minute limit is exceeded."""
    limit = limit_per_min if limit_per_min is not None else config.RATE_LIMIT_PER_MIN
    if limit <= 0:
        return True
    now = time.time()
    window_start = now - 60
    with _rl_lock:
        hits = [t for t in _buckets.get(identity, []) if t >= window_start]
        if len(hits) >= limit:
            _buckets[identity] = hits
            return False
        hits.append(now)
        _buckets[identity] = hits
        return True


def reset_rate_limits() -> None:
    with _rl_lock:
        _buckets.clear()
