"""Tests for the multi-agent orchestrator (orchestrator.py)."""

import asyncio

from agentic import orchestrator
from data import projectbuilder


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
        if self._replies:
            return self._replies.pop(0)
        return {"content": "done", "tool_calls": []}


def _call(cid, name, args=None):
    return {"id": cid, "name": name, "arguments": args or {}}


def test_supervisor_delegates_to_data_specialist():
    project = _project()
    chat = ScriptedLLM([
        # 1) supervisor delegates to data specialist
        {"content": None, "tool_calls": [
            _call("s1", "ask_data_specialist", {"sub_question": "top ticket categories?"})]},
        # 2) data specialist calls a connector tool
        {"content": None, "tool_calls": [_call("d1", "get_ticketing_summary")]},
        # 3) data specialist final answer
        {"content": "Top category is billing.", "tool_calls": []},
        # 4) supervisor synthesises
        {"content": "Summary: billing is the top support category.", "tool_calls": []},
    ])
    result = asyncio.run(
        orchestrator.run_orchestrator(project, "What are the top issues?",
                                      allow_search=False, chat_fn=chat)
    )
    assert result["mode"] == "orchestrator"
    assert "ask_data_specialist" in result["specialistsUsed"]
    assert "Ticketing Demo Dataset" in result["sources"]
    assert "billing" in result["content"].lower()


def test_orchestrator_streams_delegate_events():
    project = _project()
    chat = ScriptedLLM([
        {"content": None, "tool_calls": [
            _call("s1", "ask_knowledge_specialist", {"sub_question": "what does the bank do?"})]},
        {"content": "It is a retail bank.", "tool_calls": []},  # knowledge specialist final
        {"content": "The bank offers retail banking.", "tool_calls": []},  # supervisor final
    ])
    events = []

    async def emit(ev):
        events.append(ev)

    asyncio.run(orchestrator.run_orchestrator(
        project, "What does the company do?", allow_search=False, chat_fn=chat, emit=emit))
    types = [e["type"] for e in events]
    assert "delegate" in types
    assert "delegate_result" in types
    assert types[-1] == "final"
