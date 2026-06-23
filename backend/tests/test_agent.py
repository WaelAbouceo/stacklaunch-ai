"""Tests for the tool-calling agent loop (agent.py) using a scripted fake LLM."""

import asyncio

from agentic import agent
from data import projectbuilder


def _project() -> dict:
    scan = {
        "websiteUrl": "https://example-bank.com",
        "siteSummary": "A retail bank.",
        "knowledgeBase": {
            "pagesIndexed": 1,
            "pages": [
                {"title": "Personal Loans", "url": "https://example-bank.com/loans",
                 "summary": "Apply for a personal loan.", "topics": ["loan"], "content": "loan"},
            ],
        },
    }
    return projectbuilder.build_project(scan, "Example Bank", "banking", confidence=1.0)


class ScriptedLLM:
    """Returns a queued sequence of normalised chat replies, ignoring inputs."""

    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = 0

    async def __call__(self, messages, schemas):
        self.calls += 1
        if self._replies:
            return self._replies.pop(0)
        return {"content": "done", "tool_calls": []}


def _tool_call(call_id, name, arguments=None):
    return {"id": call_id, "name": name, "arguments": arguments or {}}


def test_agent_calls_tools_then_answers():
    project = _project()
    chat = ScriptedLLM([
        {"content": None, "tool_calls": [_tool_call("c1", "get_ticketing_summary")]},
        {"content": "Top issues are billing and delays.", "tool_calls": []},
    ])
    result = asyncio.run(
        agent.run_agent(project, "What are the top support issues?",
                        allow_search=False, chat_fn=chat)
    )
    assert result["mode"] == "agent"
    assert result["content"] == "Top issues are billing and delays."
    assert "Ticketing Demo Dataset" in result["sources"]
    assert "get_ticketing_summary" in result["toolsUsed"]
    assert result["observabilityDelta"].get("ticketingQueries") == 1
    assert result["observabilityDelta"].get("totalAssistantAnswers") == 1
    # An assistant_answered audit event is always present.
    assert any(e["type"] == "assistant_answered" for e in result["auditEvents"])


def test_agent_combines_multiple_tools_and_dedupes_sources():
    project = _project()
    chat = ScriptedLLM([
        {"content": None, "tool_calls": [
            _tool_call("a", "get_crm_summary"),
            _tool_call("b", "list_at_risk_customers"),
        ]},
        {"content": "12 at-risk customers; prioritise high LTV.", "tool_calls": []},
    ])
    result = asyncio.run(
        agent.run_agent(project, "Who is at risk of churn?",
                        allow_search=False, chat_fn=chat)
    )
    # Both tools tag CRM as the source; it should appear exactly once.
    assert result["sources"].count("CRM Demo Dataset") == 1
    assert result["observabilityDelta"].get("piiMaskingEvents") == 1
    assert any(e["type"] == "pii_masking_applied" for e in result["auditEvents"])


def test_agent_falls_back_when_model_returns_no_prose():
    project = _project()
    # Model immediately returns empty content and no tool calls.
    chat = ScriptedLLM([{"content": "", "tool_calls": []}])
    result = asyncio.run(
        agent.run_agent(project, "Tell me about the bank",
                        allow_search=False, chat_fn=chat)
    )
    assert result["mode"].startswith("fallback")
    assert result["content"]


def test_agent_streams_events_via_emit():
    project = _project()
    chat = ScriptedLLM([
        {"content": None, "tool_calls": [_tool_call("c1", "get_erp_summary")]},
        {"content": "Revenue looks healthy.", "tool_calls": []},
    ])
    events = []

    async def emit(ev):
        events.append(ev)

    asyncio.run(
        agent.run_agent(project, "How is revenue?", allow_search=False,
                        chat_fn=chat, emit=emit)
    )
    types = [e["type"] for e in events]
    assert "tool_call" in types
    assert "tool_result" in types
    assert types[-1] == "final"


def test_agent_includes_prior_history_in_context():
    """Follow-ups ("how did you reach this?") must see earlier turns."""
    project = _project()
    captured: dict = {}

    class Capturing:
        def __init__(self, reply):
            self.reply = reply

        async def __call__(self, messages, schemas):
            captured["messages"] = messages
            return self.reply

    history = [
        {"role": "user", "content": "Summarize KYC support trends."},
        {"role": "assistant", "content": "KYC Pending is 17 tickets, 51.7% negative."},
    ]
    chat = Capturing({"content": "I used the get_ticketing_summary figures.", "tool_calls": []})
    result = asyncio.run(
        agent.run_agent(project, "how did you reach this?", allow_search=False,
                        chat_fn=chat, history=history)
    )
    contents = [m.get("content") for m in captured["messages"]]
    assert "KYC Pending is 17 tickets, 51.7% negative." in contents
    assert "Summarize KYC support trends." in contents
    # The new question is always the final message.
    assert captured["messages"][-1]["content"] == "how did you reach this?"
    assert result["content"] == "I used the get_ticketing_summary figures."


def test_agent_knows_caller_role():
    """The signed-in role is injected so 'who am I?' is answerable."""
    project = _project()
    captured: dict = {}

    class Capturing:
        def __init__(self, reply):
            self.reply = reply

        async def __call__(self, messages, schemas):
            captured["messages"] = messages
            return self.reply

    chat = Capturing({"content": "You are signed in as the CFO.", "tool_calls": []})
    asyncio.run(
        agent.run_agent(project, "who am i?", allow_search=False,
                        chat_fn=chat, caller_role="CFO")
    )
    assert "CFO" in captured["messages"][0]["content"]


def test_agent_handles_unknown_tool_gracefully():
    project = _project()
    chat = ScriptedLLM([
        {"content": None, "tool_calls": [_tool_call("c1", "nonexistent_tool")]},
        {"content": "Answered despite the bad tool.", "tool_calls": []},
    ])
    result = asyncio.run(
        agent.run_agent(project, "anything", allow_search=False, chat_fn=chat)
    )
    assert result["content"] == "Answered despite the bad tool."
