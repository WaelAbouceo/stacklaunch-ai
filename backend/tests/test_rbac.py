"""Tests for RBAC permission logic (rbac.py)."""

from governance import rbac


def test_owner_has_full_access():
    perms = rbac.permissions_for("Owner")
    assert rbac.has_permission(perms, "read:connectors:aggregated")
    assert rbac.has_permission(perms, "write:all")
    # Owner is full-access via the "*" wildcard.
    assert rbac.has_permission(perms, "use:assistant")
    assert rbac.has_permission(perms, "manage:keys")


def test_action_level_wildcard():
    granted = {"read:all"}
    assert rbac.has_permission(granted, "read:connectors:aggregated")
    assert rbac.has_permission(granted, "read:knowledge")
    assert not rbac.has_permission(granted, "write:all")


def test_viewer_is_restricted():
    perms = rbac.permissions_for("Viewer")
    assert rbac.has_permission(perms, "read:knowledge")
    assert not rbac.has_permission(perms, "read:connectors:aggregated")
    assert not rbac.has_permission(perms, "manage:keys")


def test_has_any_accepts_alternatives():
    perms = rbac.permissions_for("Support Agent")
    # Support Agent has read:ticketing:aggregated but not read:connectors:aggregated.
    assert rbac.has_any(perms, ["read:connectors:aggregated", "read:ticketing:aggregated"])
    assert not rbac.has_any(perms, ["read:connectors:aggregated"])


def test_empty_requirement_is_open():
    assert rbac.has_any(set(), [])
