"""Tests for API-key auth + rate limiting (security.py)."""

import pytest

from governance import security


@pytest.fixture()
def keystore(tmp_path):
    security.configure(str(tmp_path / "app.db"))
    security.reset_rate_limits()
    yield security
    security.configure(security.config.APP_DB_PATH)


def test_create_and_resolve_key(keystore):
    created = keystore.create_key("analyst laptop", "Analyst")
    assert created["apiKey"].startswith("sk-sl-")
    principal = keystore.resolve(created["apiKey"])
    assert principal is not None
    assert principal.role == "Analyst"
    assert principal.authenticated is True
    assert "use:assistant" in principal.permissions


def test_invalid_key_resolves_none(keystore):
    assert keystore.resolve("sk-sl-deadbeef") is None
    assert keystore.resolve(None) is None


def test_unknown_role_rejected(keystore):
    with pytest.raises(ValueError):
        keystore.create_key("bad", "Wizard")


def test_revoked_key_stops_resolving(keystore):
    created = keystore.create_key("temp", "Viewer")
    key_id = keystore.list_keys()[0]["id"]
    assert keystore.resolve(created["apiKey"]) is not None
    assert keystore.revoke_key(key_id) is True
    assert keystore.resolve(created["apiKey"]) is None


def test_rate_limit_blocks_after_threshold(keystore):
    assert keystore.check_rate_limit("user-a", limit_per_min=3)
    assert keystore.check_rate_limit("user-a", limit_per_min=3)
    assert keystore.check_rate_limit("user-a", limit_per_min=3)
    assert keystore.check_rate_limit("user-a", limit_per_min=3) is False
    # A different identity is unaffected.
    assert keystore.check_rate_limit("user-b", limit_per_min=3)
