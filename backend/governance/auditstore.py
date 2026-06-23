"""Persisted, tamper-evident audit log (SQLite + hash chain).

Every audit event is appended to a SQLite table and linked to the previous row by
a SHA-256 hash chain:

    row.hash = sha256(prev_hash + canonical(event_fields))

Because each hash incorporates the prior hash, altering or deleting any historical
row invalidates every subsequent hash — `verify_chain()` detects exactly where.
This turns the previously ephemeral audit events into a compliance-grade,
append-only trail without any heavy infrastructure (single local file).

Thread-safe via a module lock so it is safe to call from FastAPI's threadpool /
event loop. Configurable DB path via AUDIT_DB_PATH (or `configure()` in tests).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import threading

from core import config

GENESIS_HASH = "0" * 64

_DEFAULT_PATH = config.AUDIT_DB_PATH
_db_path = _DEFAULT_PATH
_conn: sqlite3.Connection | None = None
_lock = threading.Lock()

# Fields that participate in the hash (NOT seq or the hash itself).
_HASHED_FIELDS = ("id", "project_id", "type", "message", "actor", "timestamp")


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(_db_path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                seq        INTEGER PRIMARY KEY AUTOINCREMENT,
                id         TEXT NOT NULL,
                project_id TEXT,
                type       TEXT NOT NULL,
                message    TEXT NOT NULL,
                actor      TEXT NOT NULL,
                timestamp  TEXT NOT NULL,
                prev_hash  TEXT NOT NULL,
                hash       TEXT NOT NULL,
                signature  TEXT NOT NULL DEFAULT ''
            )
            """
        )
        _conn.commit()
    return _conn


def configure(path: str) -> None:
    """Point the store at a different DB file and reset the connection (for tests)."""
    global _conn, _db_path
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = None
        _db_path = path


def _canonical(event: dict, project_id: str | None) -> str:
    payload = {f: ("" if event.get(f) is None else str(event.get(f))) for f in _HASHED_FIELDS}
    payload["project_id"] = project_id or ""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _compute_hash(prev_hash: str, event: dict, project_id: str | None) -> str:
    return hashlib.sha256((prev_hash + _canonical(event, project_id)).encode("utf-8")).hexdigest()


def _sign(h: str) -> str:
    return hmac.new(config.AUDIT_HMAC_SECRET.encode("utf-8"), h.encode("utf-8"), hashlib.sha256).hexdigest()


def _latest_hash(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT hash FROM audit_events ORDER BY seq DESC LIMIT 1").fetchone()
    return row["hash"] if row else GENESIS_HASH


def append_event(event: dict, project_id: str | None = None) -> dict:
    """Append one event; returns the stored record (with seq, prev_hash, hash)."""
    with _lock:
        conn = _connect()
        prev = _latest_hash(conn)
        h = _compute_hash(prev, event, project_id)
        sig = _sign(h)
        cur = conn.execute(
            """INSERT INTO audit_events
               (id, project_id, type, message, actor, timestamp, prev_hash, hash, signature)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.get("id", ""),
                project_id,
                event.get("type", ""),
                event.get("message", ""),
                event.get("actor", "system"),
                event.get("timestamp", ""),
                prev,
                h,
                sig,
            ),
        )
        conn.commit()
        return {**event, "seq": cur.lastrowid, "projectId": project_id,
                "prevHash": prev, "hash": h, "signature": sig}


def append_events(events: list[dict], project_id: str | None = None) -> list[dict]:
    return [append_event(e, project_id) for e in events]


def list_events(limit: int = 100, project_id: str | None = None) -> list[dict]:
    with _lock:
        conn = _connect()
        if project_id:
            rows = conn.execute(
                "SELECT * FROM audit_events WHERE project_id = ? ORDER BY seq DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM audit_events ORDER BY seq DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_row_to_dict(r) for r in rows]


def verify_chain() -> dict:
    """Recompute the whole chain. Returns {ok, count, brokenAtSeq, signaturesOk}.

    `ok`/`brokenAtSeq` reflect the hash chain (tamper-evidence, secret-independent).
    `signaturesOk` is True only when every row's HMAC matches the current secret —
    informational, since the default per-process secret rotates across restarts.
    """
    with _lock:
        conn = _connect()
        rows = conn.execute("SELECT * FROM audit_events ORDER BY seq ASC").fetchall()
        prev = GENESIS_HASH
        signatures_ok = True
        for r in rows:
            event = {f: r[f] for f in _HASHED_FIELDS}
            expected = _compute_hash(prev, event, r["project_id"])
            if r["prev_hash"] != prev or r["hash"] != expected:
                return {"ok": False, "count": len(rows), "brokenAtSeq": r["seq"],
                        "signaturesOk": False}
            try:
                if not hmac.compare_digest(r["signature"] or "", _sign(r["hash"])):
                    signatures_ok = False
            except (KeyError, IndexError):
                signatures_ok = False
            prev = r["hash"]
        return {"ok": True, "count": len(rows), "brokenAtSeq": None,
                "signaturesOk": signatures_ok}


def _row_to_dict(r: sqlite3.Row) -> dict:
    return {
        "seq": r["seq"],
        "id": r["id"],
        "projectId": r["project_id"],
        "type": r["type"],
        "message": r["message"],
        "actor": r["actor"],
        "timestamp": r["timestamp"],
        "prevHash": r["prev_hash"],
        "hash": r["hash"],
        "signature": r["signature"] if "signature" in r.keys() else "",
    }
