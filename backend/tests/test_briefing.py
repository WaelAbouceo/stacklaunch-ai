"""Tests for the persona-aware executive briefing + Next Best Actions."""

import asyncio

import pytest

from agentic import briefing
from core import llm
from data import projectbuilder
from governance import rbac


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    """Keep briefing tests deterministic + offline: use the fallback narrative
    instead of a live LLM call."""
    monkeypatch.setattr(llm, "is_enabled", lambda: False)


def _project() -> dict:
    scan = {"websiteUrl": "https://b.com", "siteSummary": "A retail bank.",
            "knowledgeBase": {"pagesIndexed": 1, "pages": [
                {"title": "Home", "url": "https://b.com", "summary": "Bank",
                 "topics": [], "content": "bank"}]}}
    project = projectbuilder.build_project(scan, "B Bank", "banking", 1.0)
    from data import analytics
    project["analytics"] = analytics.build_cross_source_summary(project["connectors"])
    return project


def _run(coro):
    return asyncio.run(coro)


def test_customer_gets_no_internal_data():
    project = _project()
    perms = rbac.permissions_for("Customer")
    b = _run(briefing.build_briefing(project, perms, "Customer"))
    assert b["hasData"] is False
    assert b["kpis"] == []
    assert b["actions"] == []
    assert b["suggestedQuestions"]  # public questions still offered


def test_cfo_gets_kpis_and_actions():
    project = _project()
    perms = rbac.permissions_for("CFO")
    b = _run(briefing.build_briefing(project, perms, "CFO"))
    assert b["hasData"] is True
    assert len(b["kpis"]) >= 4
    assert all({"label", "value", "tone"} <= set(k) for k in b["kpis"])
    # Actions are present, capped, and carry a ready-made prompt + evidence.
    assert 0 < len(b["actions"]) <= 5
    for a in b["actions"]:
        assert a["suggestedPrompt"]
        assert a["severity"] in {"high", "medium", "low"}
        assert a["sources"]


def test_actions_ranked_by_severity():
    project = _project()
    perms = rbac.permissions_for("CEO")
    b = _run(briefing.build_briefing(project, perms, "CEO"))
    ranks = [briefing._SEVERITY_RANK[a["severity"]] for a in b["actions"]]
    assert ranks == sorted(ranks, reverse=True)


def test_narrative_present_without_llm():
    # No LLM configured in tests -> deterministic narrative must still be returned.
    project = _project()
    perms = rbac.permissions_for("Accountant")
    b = _run(briefing.build_briefing(project, perms, "Accountant"))
    assert isinstance(b["narrative"], str) and len(b["narrative"]) > 0
