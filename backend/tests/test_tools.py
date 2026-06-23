"""Tests for the governed tool registry (tools.py)."""

import asyncio

from data import analytics
from data import projectbuilder
from agentic import tools as tools_module
from agentic.tools import ToolContext


def _project() -> dict:
    scan = {
        "websiteUrl": "https://example-bank.com",
        "siteSummary": "A retail bank.",
        "knowledgeBase": {
            "pagesIndexed": 2,
            "pages": [
                {"title": "Personal Loans", "url": "https://example-bank.com/loans",
                 "summary": "Apply for a personal loan.", "topics": ["loan"], "content": "loan loan loan"},
                {"title": "Branches", "url": "https://example-bank.com/branches",
                 "summary": "Find a branch.", "topics": ["branch"], "content": "branch locations"},
            ],
        },
    }
    return projectbuilder.build_project(scan, "Example Bank", "banking", confidence=1.0)


def _ctx(allow_search: bool = True) -> ToolContext:
    project = _project()
    summary = analytics.build_cross_source_summary(project["connectors"])
    return ToolContext(project=project, summary=summary,
                       company=project["companyName"], allow_search=allow_search)


def _run(coro):
    return asyncio.run(coro)


def test_registry_shapes_are_valid_openai_schemas():
    tools = tools_module.build_registry(allow_search=True)
    names = {t.name for t in tools}
    assert "get_crm_summary" in names
    assert "web_search" in names
    for t in tools:
        schema = t.to_openai_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == t.name
        assert "parameters" in schema["function"]


def test_web_search_excluded_when_disabled():
    tools = tools_module.build_registry(allow_search=False)
    assert "web_search" not in {t.name for t in tools}


def test_connector_summary_tools_return_aggregates():
    ctx = _ctx()
    by_name = tools_module.registry_by_name(tools_module.build_registry())
    crm = _run(by_name["get_crm_summary"].run(ctx, {}))
    assert "bySegment" in crm and "atRiskCount" in crm
    erp = _run(by_name["get_erp_summary"].run(ctx, {}))
    assert "totalRevenueEgp" in erp and "lowestMargin" in erp
    tickets = _run(by_name["get_ticketing_summary"].run(ctx, {}))
    assert "byCategory" in tickets and "negativeRate" in tickets


def test_at_risk_customers_are_pii_masked():
    ctx = _ctx()
    by_name = tools_module.registry_by_name(tools_module.build_registry())
    out = _run(by_name["list_at_risk_customers"].run(ctx, {}))
    for cust in out["customers"]:
        assert "customerId" in cust
        # PII must never leak through this governed tool.
        assert "name" not in cust
        assert "email" not in cust
        assert "phone" not in cust


def test_search_knowledge_base_finds_real_pages():
    ctx = _ctx()
    by_name = tools_module.registry_by_name(tools_module.build_registry())
    out = _run(by_name["search_knowledge_base"].run(ctx, {"query": "personal loan"}))
    assert any("Loans" in m["title"] for m in out["matches"])


def test_web_search_is_a_noop_when_disabled():
    ctx = _ctx(allow_search=False)
    by_name = tools_module.registry_by_name(tools_module.build_registry(allow_search=True))
    out = _run(by_name["web_search"].run(ctx, {"query": "branches"}))
    assert out["results"] == []
