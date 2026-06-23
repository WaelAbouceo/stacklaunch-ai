"""Tests for the hash-chained audit store (auditstore.py)."""

import sqlite3

import pytest

from governance import auditstore
from governance import audit_events as governance


@pytest.fixture()
def store(tmp_path):
    auditstore.configure(str(tmp_path / "audit.db"))
    yield auditstore
    auditstore.configure(auditstore._DEFAULT_PATH)


def _event(msg: str) -> dict:
    return governance.create_audit_event("assistant_answered", msg, actor="tester")


def test_append_links_hash_chain(store):
    a = store.append_event(_event("first"), project_id="p1")
    b = store.append_event(_event("second"), project_id="p1")
    assert a["prevHash"] == auditstore.GENESIS_HASH
    assert b["prevHash"] == a["hash"]
    assert a["hash"] != b["hash"]


def test_verify_passes_for_intact_chain(store):
    store.append_events([_event("a"), _event("b"), _event("c")], project_id="p1")
    report = store.verify_chain()
    assert report["ok"] is True
    assert report["count"] == 3
    assert report["brokenAtSeq"] is None


def test_verify_detects_tampering(store):
    store.append_events([_event("a"), _event("b"), _event("c")], project_id="p1")
    # Tamper with the message of row 2 directly in the DB.
    conn = sqlite3.connect(store._db_path)
    conn.execute("UPDATE audit_events SET message = 'HACKED' WHERE seq = 2")
    conn.commit()
    conn.close()
    report = store.verify_chain()
    assert report["ok"] is False
    assert report["brokenAtSeq"] == 2


def test_list_filters_by_project(store):
    store.append_event(_event("x"), project_id="p1")
    store.append_event(_event("y"), project_id="p2")
    p1 = store.list_events(project_id="p1")
    assert len(p1) == 1
    assert p1[0]["projectId"] == "p1"


def test_list_returns_newest_first(store):
    store.append_event(_event("old"), project_id="p1")
    store.append_event(_event("new"), project_id="p1")
    events = store.list_events()
    assert events[0]["message"] == "new"


def test_signatures_ok_for_fresh_signed_chain(store):
    rows = store.append_events([_event("a"), _event("b")], project_id="p1")
    assert all(r["signature"] for r in rows)
    report = store.verify_chain()
    assert report["ok"] is True
    assert report["signaturesOk"] is True


def test_tampered_signature_is_detected(store):
    store.append_events([_event("a"), _event("b")], project_id="p1")
    conn = sqlite3.connect(store._db_path)
    conn.execute("UPDATE audit_events SET signature = 'forged' WHERE seq = 1")
    conn.commit()
    conn.close()
    report = store.verify_chain()
    # Hash chain is still intact, but the signature no longer matches the secret.
    assert report["ok"] is True
    assert report["signaturesOk"] is False
