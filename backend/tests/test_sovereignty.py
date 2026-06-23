"""Sovereign egress / data-residency controls."""

from core import config
from core import llm
from governance import sovereignty


# --- SSRF / egress guard --------------------------------------------------

def test_blocks_cloud_metadata_endpoint():
    assert not sovereignty.is_safe_target("http://169.254.169.254/latest/meta-data/")


def test_blocks_loopback_and_private_ranges():
    assert not sovereignty.is_safe_target("http://127.0.0.1/")
    assert not sovereignty.is_safe_target("http://10.0.0.5/")
    assert not sovereignty.is_safe_target("https://192.168.1.1/admin")


def test_blocks_non_http_schemes():
    assert not sovereignty.is_safe_target("ftp://example.com/")
    assert not sovereignty.is_safe_target("file:///etc/passwd")


def test_allows_public_address():
    # IP literal -> no DNS / network needed; 1.1.1.1 is public.
    assert sovereignty.is_safe_target("http://1.1.1.1/")


def test_assert_raises_egress_blocked():
    try:
        sovereignty.assert_safe_target("http://169.254.169.254/")
    except sovereignty.EgressBlocked:
        return
    raise AssertionError("expected EgressBlocked")


def test_private_scan_override(monkeypatch):
    monkeypatch.setattr(config, "ALLOW_PRIVATE_SCAN", True)
    assert sovereignty.is_safe_target("http://127.0.0.1/")


# --- LLM host classification ----------------------------------------------

def test_external_llm_detection():
    assert sovereignty.is_external_llm("api.openai.com")
    assert sovereignty.is_external_llm("eu.api.openai.com")  # subdomain
    assert not sovereignty.is_external_llm("sovereigneg.com")
    assert not sovereignty.is_external_llm(None)


def test_residency_classification():
    assert sovereignty.classify_residency("sovereigneg.com")["code"] == "sovereign"
    assert sovereignty.classify_residency("localhost")["code"] == "self_hosted"
    assert sovereignty.classify_residency("api.openai.com")["code"] == "external"
    assert sovereignty.classify_residency(None)["code"] == "none"


def test_host_of():
    assert sovereignty.host_of("https://sovereigneg.com/v1") == "sovereigneg.com"
    assert sovereignty.host_of("http://localhost:8080") == "localhost"
    assert sovereignty.host_of(None) is None


# --- Startup validation ---------------------------------------------------

def test_strict_mode_rejects_unallowed_external_llm(monkeypatch):
    monkeypatch.setattr(config, "SOVEREIGN_STRICT", True)
    monkeypatch.setattr(config, "ALLOW_EXTERNAL_LLM", False)
    monkeypatch.setattr(llm, "provider_info", lambda: {"host": "api.openai.com", "provider": "x", "model": "m"})
    try:
        sovereignty.validate_startup()
    except sovereignty.EgressBlocked:
        return
    raise AssertionError("expected strict mode to reject external LLM")


def test_non_strict_external_llm_warns_not_raises(monkeypatch):
    monkeypatch.setattr(config, "SOVEREIGN_STRICT", False)
    monkeypatch.setattr(config, "ALLOW_EXTERNAL_LLM", False)
    monkeypatch.setattr(llm, "provider_info", lambda: {"host": "api.openai.com", "provider": "x", "model": "m"})
    warnings = sovereignty.validate_startup()
    assert any("non-sovereign" in w for w in warnings)


# --- Posture manifest -----------------------------------------------------

def test_posture_manifest_shape():
    p = sovereignty.posture()
    assert p["dataRegion"]
    assert p["egress"]["scanSsrfGuard"] is True
    assert "appDb" in p["dataAtRest"]
    assert p["controls"]["piiRedaction"] is True
    assert "residency" in p["llm"]
