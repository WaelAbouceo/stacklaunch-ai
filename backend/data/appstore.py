"""Persistence for projects and conversation memory (SQLite).

Gives the previously-stateless backend durable storage for built projects and
per-session conversation memory, plus **right-to-erasure** support (purge a
project's data and a session's memory) for data-retention compliance.

Lightweight by design: one local SQLite file (shared with the rest of the app via
config.APP_DB_PATH), JSON-encoded project blobs, thread-safe via a module lock.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time

from core import config

_db_path = config.APP_DB_PATH
_conn: sqlite3.Connection | None = None
_lock = threading.Lock()


def configure(path: str) -> None:
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
        _conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id         TEXT PRIMARY KEY,
                company    TEXT,
                industry   TEXT,
                website    TEXT,
                created_at REAL,
                data       TEXT
            );
            CREATE TABLE IF NOT EXISTS memory (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                project_id TEXT,
                role       TEXT NOT NULL,
                content    TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_memory_session ON memory(session_id);
            """
        )
        _conn.commit()
    return _conn


# --- Projects -------------------------------------------------------------


def save_project(project: dict) -> None:
    with _lock:
        conn = _connect()
        conn.execute(
            """INSERT OR REPLACE INTO projects (id, company, industry, website, created_at, data)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                project.get("id"),
                project.get("companyName"),
                project.get("industry"),
                project.get("websiteUrl"),
                time.time(),
                json.dumps(project, default=str),
            ),
        )
        conn.commit()


def get_project(project_id: str) -> dict | None:
    with _lock:
        conn = _connect()
        row = conn.execute("SELECT data FROM projects WHERE id = ?", (project_id,)).fetchone()
        return json.loads(row["data"]) if row else None


def list_projects() -> list[dict]:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT id, company, industry, website, created_at FROM projects ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def delete_project(project_id: str) -> dict:
    """Right-to-erasure: remove a project and its conversation memory."""
    with _lock:
        conn = _connect()
        p = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,)).rowcount
        m = conn.execute("DELETE FROM memory WHERE project_id = ?", (project_id,)).rowcount
        conn.commit()
        return {"projectsDeleted": p, "memoryRowsDeleted": m}


# --- Conversation memory --------------------------------------------------


def add_turn(session_id: str, role: str, content: str, project_id: str | None = None) -> None:
    if not session_id:
        return
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT INTO memory (session_id, project_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, project_id, role, content, time.time()),
        )
        conn.commit()


def get_turns(session_id: str, limit: int = 6) -> list[dict]:
    if not session_id:
        return []
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT role, content FROM memory WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def get_session_project_id(session_id: str) -> str | None:
    """The most recent project a session's turns were recorded against."""
    if not session_id:
        return None
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT project_id FROM memory WHERE session_id = ? AND project_id IS NOT NULL "
            "ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        return row["project_id"] if row else None


def clear_session(session_id: str) -> int:
    with _lock:
        conn = _connect()
        c = conn.execute("DELETE FROM memory WHERE session_id = ?", (session_id,)).rowcount
        conn.commit()
        return c
