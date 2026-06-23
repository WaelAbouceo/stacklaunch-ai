"""Tests for the evaluation harness + RBAC enforcement inside the agent loop."""

import asyncio

from agentic import agent
from evaluation import evals
from data import projectbuilder
from governance import rbac


def test_golden_evals_pass():
    report = evals.run_evals()
    assert report["total"] == len(evals.GOLDEN)
    # The deterministic assistant should pass the full golden set.
    assert report["passed"] == report["total"], report


def _project() -> dict:
    scan = {"websiteUrl": "https://b.com", "siteSummary": "Bank",
            "knowledgeBase": {"pagesIndexed": 1, "pages": [
                {"title": "Home", "url": "https://b.com", "summary": "Bank",
                 "topics": [], "content": "bank"}]}}
    return projectbuilder.build_project(scan, "B Bank", "banking", 1.0)


class ScriptedLLM:
    def __init__(self, replies):
        self._replies = list(replies)

    async def __call__(self, messages, schemas):
        return self._replies.pop(0) if self._replies else {"content": "done", "tool_calls": []}


def test_agent_denies_tool_without_permission():
    project = _project()
    chat = ScriptedLLM([
        {"content": None, "tool_calls": [
            {"id": "c1", "name": "get_crm_summary", "arguments": {}}]},
        {"content": "I could not access CRM data.", "tool_calls": []},
    ])
    # Viewer can only read:knowledge, so the CRM tool must be denied.
    viewer_perms = rbac.permissions_for("Viewer")
    result = asyncio.run(agent.run_agent(
        project, "How many customers?", allow_search=False,
        permissions=viewer_perms, chat_fn=chat))
    assert result["observabilityDelta"].get("guardrailBlocks") == 1
    assert "get_crm_summary" not in result["toolsUsed"]
    assert any(e["type"] == "guardrail_triggered" for e in result["auditEvents"])
