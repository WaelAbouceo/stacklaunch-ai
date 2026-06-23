"""Tests for the enterprise seat model and the seat-login endpoints."""

import pytest
from fastapi.testclient import TestClient

from governance import orgmodel
from governance import security


@pytest.fixture()
def client(tmp_path):
    # Mint seat keys into a throwaway DB so tests don't pollute app.db.
    security.configure(str(tmp_path / "auth.db"))
    import main
    with TestClient(main.app) as c:
        yield c
    security.configure(security.config.APP_DB_PATH)


# --- Seat access derivation (pure logic) ----------------------------------

def test_clearance_ladder_is_ordered():
    assert orgmodel.clearance_level("public") < orgmodel.clearance_level("internal")
    assert orgmodel.clearance_level("internal") < orgmodel.clearance_level("confidential")
    assert orgmodel.clearance_level("confidential") < orgmodel.clearance_level("restricted")
    assert orgmodel.clearance_allows("confidential", "internal")
    assert not orgmodel.clearance_allows("internal", "restricted")


def test_external_seat_is_least_privilege():
    acc = orgmodel.derive_access("external")
    assert acc["clearance"] == "public"
    assert rbac_has(acc, "use:assistant")
    assert rbac_has(acc, "read:knowledge")
    assert not rbac_has(acc, "read:connectors:aggregated")
    assert not rbac_has(acc, "view:audit")
    assert acc["department"] is None


def test_member_seat_is_department_scoped_aggregates():
    acc = orgmodel.derive_access("member", "Finance")
    assert acc["clearance"] == "internal"
    assert acc["department"] == "Finance"
    assert rbac_has(acc, "read:connectors:aggregated")
    assert not rbac_has(acc, "manage:connectors")
    assert not rbac_has(acc, "view:audit")


def test_department_head_provisions_and_audits():
    acc = orgmodel.derive_access("department", "Finance")
    assert acc["clearance"] == "restricted"
    assert rbac_has(acc, "manage:connectors")
    assert rbac_has(acc, "view:audit")
    assert rbac_has(acc, "manage:keys")


def test_system_seat_is_wildcard_and_unscoped():
    acc = orgmodel.derive_access("system", "Finance")  # scope ignored for system
    assert acc["permissions"] == {"*"}
    assert acc["department"] is None
    assert acc["clearance"] == "restricted"


def rbac_has(access, perm):
    from governance import rbac
    return rbac.has_any(access["permissions"], [perm])


# --- Endpoints ------------------------------------------------------------

def test_seats_endpoint_returns_org_and_seats(client):
    res = client.get("/api/login/seats")
    assert res.status_code == 200
    body = res.json()
    assert "org" in body and "departments" in body["org"]
    labels = [s["label"] for s in body["seats"]]
    assert "System Administrator" in labels
    assert "External User" in labels


def test_login_mints_scoped_seat_key_and_me_resolves(client):
    res = client.post("/api/login", json={"tier": "department", "department": "Finance"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["adminTier"] == "department"
    assert body["department"] == "Finance"
    assert body["clearance"] == "restricted"
    assert "manage:connectors" in body["permissions"]
    key = body["apiKey"]
    assert key.startswith("sk-sl-")

    me = client.get("/api/me", headers={"X-API-Key": key})
    assert me.status_code == 200
    assert me.json()["adminTier"] == "department"
    assert me.json()["department"] == "Finance"
    assert me.json()["authenticated"] is True


def test_login_external_needs_no_department(client):
    res = client.post("/api/login", json={"tier": "external"})
    assert res.status_code == 200
    assert res.json()["clearance"] == "public"


def test_login_member_requires_department(client):
    res = client.post("/api/login", json={"tier": "member"})
    assert res.status_code == 400


def test_login_rejects_unknown_tier(client):
    res = client.post("/api/login", json={"tier": "wizard"})
    assert res.status_code == 403


# --- Scoped admin seat minting -------------------------------------------

def _dept_admin_key(client, department="Finance"):
    res = client.post("/api/login", json={"tier": "department", "department": department})
    return res.json()["apiKey"]


def test_dept_admin_mints_member_in_own_department(client):
    key = _dept_admin_key(client)
    res = client.post(
        "/api/seats/mint",
        json={"tier": "member", "department": "Finance"},
        headers={"X-API-Key": key},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["tier"] == "member"
    assert body["department"] == "Finance"
    assert body["apiKey"].startswith("sk-sl-")


def test_dept_admin_cannot_mint_outside_department(client):
    key = _dept_admin_key(client, "Finance")
    res = client.post(
        "/api/seats/mint",
        json={"tier": "member", "department": "Customer Care"},
        headers={"X-API-Key": key},
    )
    assert res.status_code == 403


def test_dept_admin_cannot_escalate_to_peer_or_above(client):
    key = _dept_admin_key(client, "Finance")
    res = client.post(
        "/api/seats/mint",
        json={"tier": "department", "department": "Finance"},
        headers={"X-API-Key": key},
    )
    assert res.status_code == 403


def test_member_cannot_mint_seats(client):
    res = client.post("/api/login", json={"tier": "member", "department": "Finance"})
    member_key = res.json()["apiKey"]
    out = client.post(
        "/api/seats/mint",
        json={"tier": "member", "department": "Finance"},
        headers={"X-API-Key": member_key},
    )
    assert out.status_code == 403  # members lack manage:keys
