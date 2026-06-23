"""Agent tool registry: governed, callable access to a project's data sources.

Each tool wraps existing analytics/retrieval logic behind a JSON-schema'd
interface the LLM can invoke. Tools are the *governed data-access layer*: PII
masking, source tagging, and audit/observability metadata all live here, so the
agent reasons over tools and can never reach raw records directly.

This is the foundation of the agentic upgrade — instead of pre-baking one data
summary into the prompt, the model decides which connectors to query, in what
order, and how to combine them.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from data import analytics
from data import database
from governance import guardrails
from governance import orgmodel
from agentic import retrieval
from data import search as search_module

# A tool handler receives the live ToolContext plus the model-supplied arguments
# and returns a JSON-serialisable dict. Handlers may be sync or async.
Handler = Callable[["ToolContext", dict], "dict | Awaitable[dict]"]


@dataclass
class ToolContext:
    """Per-request state shared by every tool invocation."""

    project: dict
    summary: dict
    company: str
    allow_search: bool = True
    # Caller org scope (enterprise RBAC). Defaults grant full reach for direct /
    # in-process calls and tests.
    clearance: str = "restricted"
    admin_tier: str | None = "system"
    department: str | None = None


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON schema for the arguments object
    handler: Handler
    sources: list[str] = field(default_factory=list)
    observability: dict = field(default_factory=dict)
    audit_types: list[str] = field(default_factory=list)
    # Any-of permissions required to call this tool (empty = unrestricted).
    permissions: list[str] = field(default_factory=list)
    # The connector this tool reads (crm/erp/ticketing), for department scoping.
    # None = not department-scoped (knowledge base, web, company overview).
    connector: str | None = None
    # True for tools that intrinsically span multiple departments (e.g. cross-source
    # joins). Only org-wide (system / unscoped) callers may use them.
    cross_department: bool = False

    def to_openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    async def run(self, ctx: ToolContext, args: dict) -> dict:
        result = self.handler(ctx, args or {})
        if inspect.isawaitable(result):
            result = await result
        return result


_NO_ARGS = {"type": "object", "properties": {}, "additionalProperties": False}


def _query_args(description: str) -> dict:
    return {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": description},
        },
        "required": ["query"],
        "additionalProperties": False,
    }


def _query_spec_schema() -> dict:
    """JSON schema for the structured query spec the LLM emits."""
    return {
        "type": "object",
        "properties": {
            "query": {
                "type": "object",
                "properties": {
                    "table": {"type": "string", "enum": ["crm", "erp", "ticketing"]},
                    "select": {"type": "array", "items": {"type": "string"},
                               "description": "Column names, or omit/['*'] for all."},
                    "aggregate": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "fn": {"type": "string",
                                       "enum": ["count", "sum", "avg", "min", "max"]},
                                "column": {"type": "string"},
                                "as": {"type": "string"},
                            },
                            "required": ["fn"],
                        },
                    },
                    "filters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "column": {"type": "string"},
                                "op": {"type": "string",
                                       "enum": ["=", "!=", ">", "<", ">=", "<=", "like", "in"]},
                                "value": {},
                            },
                            "required": ["column", "op", "value"],
                        },
                    },
                    "group_by": {"type": "array", "items": {"type": "string"}},
                    "order_by": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "column": {"type": "string"},
                                "dir": {"type": "string", "enum": ["asc", "desc"]},
                            },
                            "required": ["column"],
                        },
                    },
                    "limit": {"type": "integer"},
                },
                "required": ["table"],
            }
        },
        "required": ["query"],
    }


# --- Handlers -------------------------------------------------------------


def _company_overview(ctx: ToolContext, _args: dict) -> dict:
    project = ctx.project
    kb = project.get("knowledgeBase", {})
    pages = kb.get("pages", [])
    return {
        "company": ctx.company,
        "industry": project.get("industryLabel", ""),
        "websiteUrl": project.get("websiteUrl", ""),
        "siteSummary": project.get("siteSummary", ""),
        "pagesIndexed": kb.get("pagesIndexed", len(pages)),
        "pageTitles": [p.get("title", "") for p in pages[:8]],
    }


def _search_knowledge_base(ctx: ToolContext, args: dict) -> dict:
    pages = ctx.project.get("knowledgeBase", {}).get("pages", [])
    query = str(args.get("query", "")).strip()
    # BM25 retrieval with citation offsets (traceable to an exact page span).
    citations = retrieval.search(pages, query, top_k=4)
    matches = [
        {
            "title": c.title, "url": c.url, "snippet": c.snippet,
            "score": c.score, "charStart": c.start, "charEnd": c.end,
        }
        for c in citations
    ]
    # Crawled page text is untrusted -> quarantine against prompt injection.
    matches, flagged = guardrails.quarantine_items(matches, ("snippet", "title"))
    return {
        "query": query,
        "matches": matches,
        "note": "Grounded in the real crawled website pages (BM25 + citation offsets)."
        if matches else "No indexed page matched; consider web_search if allowed.",
        "_injection": 1 if flagged else 0,
    }


# Financial / value fields that require Confidential clearance to see in raw form.
# Below that clearance they are redacted to a sentinel; aggregate counts remain.
_FINANCIAL_KEYS = {
    "totalRevenueEgp", "totalCostEgp", "avgMarginPercent",
    "revenueEgp", "costEgp", "marginPercent", "profitEgp",
    "avgLifetimeValue", "totalLifetimeValue", "lifetimeValueEgp", "lifetimeValue",
}
_REDACTED = "🔒 restricted (needs Confidential clearance)"


def _redact_financials(obj):
    """Recursively redact financial figures (used when clearance < confidential)."""
    if isinstance(obj, dict):
        return {
            k: (_REDACTED if k in _FINANCIAL_KEYS else _redact_financials(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact_financials(x) for x in obj]
    return obj


def _can_see_financials(ctx: ToolContext) -> bool:
    return orgmodel.clearance_allows(ctx.clearance, "confidential")


def _crm_summary(ctx: ToolContext, _args: dict) -> dict:
    s = ctx.summary["crm"]
    if not _can_see_financials(ctx):
        s = _redact_financials(s)
        s["_clearance"] = "Lifetime-value figures hidden — requires Confidential clearance."
    return s


def _erp_summary(ctx: ToolContext, _args: dict) -> dict:
    s = ctx.summary["erp"]
    if not _can_see_financials(ctx):
        s = _redact_financials(s)
        s["_clearance"] = "Revenue, cost and margin figures hidden — requires Confidential clearance."
    return s


def _ticketing_summary(ctx: ToolContext, _args: dict) -> dict:
    return ctx.summary["tickets"]


def _is_department_scoped(ctx: ToolContext) -> bool:
    return ctx.department is not None and ctx.admin_tier not in (None, "system")


def _cross_source_insights(ctx: ToolContext, _args: dict) -> dict:
    # Cross-source joins span CRM/ERP/ticketing (multiple departments), so only
    # organization-wide callers may run them.
    if _is_department_scoped(ctx):
        return {
            "error": "department_scope",
            "message": (
                "Cross-source insights combine data across departments and require "
                "organization-wide access. Your seat is scoped to a single department."
            ),
        }
    out = {
        "complaintsByEntity": ctx.summary["complaintsByEntity"][:8],
        "highRevenuePoorSentiment": ctx.summary["highRevenuePoorSentiment"],
    }
    if not _can_see_financials(ctx):
        out = _redact_financials(out)
        out["_clearance"] = "Revenue figures hidden — requires Confidential clearance."
    return out


def _at_risk_customers(ctx: ToolContext, _args: dict) -> dict:
    # Customer-level retention lists (even PII-masked) require Confidential clearance.
    if not _can_see_financials(ctx):
        return {
            "error": "clearance_required",
            "message": (
                "Listing at-risk customers requires Confidential clearance. Your seat "
                "can see aggregate counts only."
            ),
        }
    crm = ctx.summary["crm"]
    # atRiskHighValue is already PII-masked upstream (ID + segment + city + LTV).
    return {
        "atRiskCount": crm["atRiskCount"],
        "customers": crm["atRiskHighValue"],
        "governance": (
            "PII masked: customers are identified by ID and segment only — "
            "never name, email, or phone."
        ),
    }


def _data_schema(ctx: ToolContext, _args: dict) -> dict:
    return {
        "tables": database.schema_for(),
        "note": (
            "Use query_internal_data with a structured spec to query these tables. "
            "PII columns (crm.name/email/phone) are returned masked."
        ),
    }


def _query_internal_data(ctx: ToolContext, args: dict) -> dict:
    spec = args.get("query") or {k: v for k, v in args.items() if k != "query"}
    table = spec.get("table")
    # Department scope: a scoped caller may only query the connector their
    # department owns. System / legacy principals are cross-department.
    if table:
        owner = ctx.project.get("connectors", {}).get(table, {}).get("department")
        if not orgmodel.department_in_scope(ctx.department, ctx.admin_tier, owner):
            return {
                "error": "department_scope",
                "message": (
                    f"The '{table}' data belongs to {owner}. Your seat is scoped to "
                    f"{ctx.department or 'your department'} and cannot query it."
                ),
            }
    try:
        out = database.run_query(ctx.project["connectors"], spec)
    except database.QueryError as exc:
        return {"error": "invalid_query", "message": str(exc),
                "schema": database.schema_for()}
    # Clearance: hide financial figures from sub-Confidential seats.
    if not _can_see_financials(ctx):
        out = _redact_financials(out)
        out["_clearance"] = "Financial columns hidden — requires Confidential clearance."
    return out


async def _web_search(ctx: ToolContext, args: dict) -> dict:
    query = str(args.get("query", "")).strip()
    if not ctx.allow_search:
        return {"query": query, "results": [], "note": "Web search is disabled for this request."}
    full_query = f"{ctx.company} {query}".strip()
    results = await search_module.search(full_query, max_results=5)
    items = [
        {"title": r.title, "url": r.url, "snippet": r.content[:400]} for r in results
    ]
    # Web results are untrusted -> quarantine against prompt injection.
    items, flagged = guardrails.quarantine_items(items, ("snippet", "title"))
    return {
        "query": full_query,
        "results": items,
        "note": "External web results via SearXNG (approved web source).",
        "_injection": 1 if flagged else 0,
    }


# --- Registry -------------------------------------------------------------


def build_registry(*, allow_search: bool = True) -> list[Tool]:
    """Return the full tool catalogue. `allow_search` excludes web_search when off."""
    tools: list[Tool] = [
        Tool(
            name="get_company_overview",
            description=(
                "Get the company's name, industry, website summary, and the titles of "
                "the real pages indexed from its website. Use this first for questions "
                "about who the company is or what it does."
            ),
            parameters=_NO_ARGS,
            handler=_company_overview,
            sources=["Website Knowledge"],
            observability={"knowledgeQueries": 1},
            audit_types=["knowledge_base_built"],
            permissions=["read:knowledge"],
        ),
        Tool(
            name="search_knowledge_base",
            description=(
                "Semantic keyword search over the real crawled website pages. Use for "
                "questions whose answer should come from the company's own website."
            ),
            parameters=_query_args("What to look for in the website knowledge base."),
            handler=_search_knowledge_base,
            sources=["Website Knowledge"],
            observability={"knowledgeQueries": 1},
            audit_types=["knowledge_base_built"],
            permissions=["read:knowledge"],
        ),
        Tool(
            name="get_crm_summary",
            description=(
                "Aggregated CRM analytics: customers by segment and status, at-risk "
                "count, and average lifetime value (EGP). No raw customer records."
            ),
            parameters=_NO_ARGS,
            handler=_crm_summary,
            sources=["CRM Demo Dataset"],
            observability={"connectorQueries": 1, "crmQueries": 1},
            audit_types=["connector_query_executed"],
            permissions=["read:connectors:aggregated"],
            connector="crm",
        ),
        Tool(
            name="get_erp_summary",
            description=(
                "Aggregated ERP analytics: revenue, cost, margins, utilization, and the "
                "lowest-margin / lowest-utilization operational entities."
            ),
            parameters=_NO_ARGS,
            handler=_erp_summary,
            sources=["ERP Demo Dataset"],
            observability={"connectorQueries": 1, "erpQueries": 1},
            audit_types=["connector_query_executed"],
            permissions=["read:connectors:aggregated"],
            connector="erp",
        ),
        Tool(
            name="get_ticketing_summary",
            description=(
                "Aggregated support-ticket analytics: volume by category, sentiment, "
                "SLA status, priority, channel, negative rate, and open/escalated count."
            ),
            parameters=_NO_ARGS,
            handler=_ticketing_summary,
            sources=["Ticketing Demo Dataset"],
            observability={"connectorQueries": 1, "ticketingQueries": 1},
            audit_types=["connector_query_executed"],
            permissions=["read:connectors:aggregated", "read:ticketing:aggregated"],
            connector="ticketing",
        ),
        Tool(
            name="get_cross_source_insights",
            description=(
                "Cross-source joins: complaints per operational entity, and entities "
                "that combine high revenue with poor sentiment. Use for questions that "
                "relate complaints/revenue across CRM, ERP, and ticketing."
            ),
            parameters=_NO_ARGS,
            handler=_cross_source_insights,
            sources=["ERP Demo Dataset", "Ticketing Demo Dataset"],
            observability={"connectorQueries": 1, "erpQueries": 1, "ticketingQueries": 1,
                           "crossSourceAnswers": 1},
            audit_types=["cross_source_insight_generated"],
            permissions=["read:connectors:aggregated"],
            cross_department=True,
        ),
        Tool(
            name="list_at_risk_customers",
            description=(
                "List the highest-value at-risk customers for retention outreach. "
                "Returns PII-masked records (ID + segment + city + lifetime value)."
            ),
            parameters=_NO_ARGS,
            handler=_at_risk_customers,
            sources=["CRM Demo Dataset"],
            observability={"connectorQueries": 1, "crmQueries": 1, "piiMaskingEvents": 1},
            audit_types=["connector_query_executed", "pii_masking_applied"],
            permissions=["read:connectors:aggregated"],
            connector="crm",
        ),
        Tool(
            name="get_data_schema",
            description=(
                "List the internal database tables (crm, erp, ticketing) and their "
                "columns. Call this before query_internal_data to know what to query."
            ),
            parameters=_NO_ARGS,
            handler=_data_schema,
            sources=["Internal Database"],
            observability={"connectorQueries": 1},
            audit_types=["connector_query_executed"],
            permissions=["read:connectors:aggregated"],
        ),
        Tool(
            name="query_internal_data",
            description=(
                "Run an ad-hoc structured query against the internal records (CRM/ERP/"
                "ticketing). Provide a `query` object: {table, select:[cols] or '*', "
                "aggregate:[{fn,column,as}], filters:[{column,op,value}], group_by:[cols], "
                "order_by:[{column,dir}], limit}. Read-only and PII-masked. Use this to "
                "extract specific rows or custom aggregates the summary tools don't cover."
            ),
            parameters=_query_spec_schema(),
            handler=_query_internal_data,
            sources=["Internal Database"],
            observability={"connectorQueries": 1, "piiMaskingEvents": 1},
            audit_types=["connector_query_executed", "pii_masking_applied"],
            permissions=["read:connectors:aggregated"],
        ),
    ]
    if allow_search:
        tools.append(
            Tool(
                name="web_search",
                description=(
                    "Search the public web (via SearXNG) for facts not on the company's "
                    "own indexed pages — e.g. branch locations, public news. Use sparingly "
                    "and only when the knowledge base lacks the answer."
                ),
                parameters=_query_args("The web search query (company name is added automatically)."),
                handler=_web_search,
                sources=["Approved Web Source"],
                observability={"knowledgeQueries": 1},
                audit_types=["knowledge_base_built"],
                permissions=["read:knowledge"],
            )
        )
    return tools


def registry_by_name(tools: list[Tool]) -> dict[str, Tool]:
    return {t.name: t for t in tools}
