"""Persona-aware executive briefing + Next Best Actions.

Turns the raw cross-source analytics into a role-tailored landing experience:

- **Narrative** — a short, grounded briefing for the signed-in role (LLM-written
  when available, deterministic template otherwise).
- **KPIs** — headline numbers computed from the connector summaries.
- **Next Best Actions** — a ranked, evidence-backed action list (churn exposure,
  SLA breaches, margin erosion, complaint hotspots, revenue-at-risk), each with a
  ready-made prompt the user can hand to the assistant.

Everything is permission-scoped: a persona that can't see internal connector data
(e.g. Customer) receives only a public welcome + suggested questions, never KPIs
or actions. This keeps the briefing aligned with the same RBAC the agent enforces.
"""

from __future__ import annotations

from data import analytics
from agentic import assistant
from core import llm
from governance import rbac

# Severity is ordered so the UI and ranking agree.
_SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}


def _tone_for(value: float, *, warn: float, danger: float, higher_is_bad: bool = True) -> str:
    if higher_is_bad:
        if value >= danger:
            return "danger"
        if value >= warn:
            return "warning"
        return "positive"
    # lower is bad
    if value <= danger:
        return "danger"
    if value <= warn:
        return "warning"
    return "positive"


def _kpis(s: dict) -> list[dict]:
    crm, erp, tk = s["crm"], s["erp"], s["tickets"]
    return [
        {"label": "Total revenue", "value": assistant.fmt_egp(erp["totalRevenueEgp"]),
         "sub": f"{erp['total']} units", "tone": "neutral"},
        {"label": "Avg margin", "value": f"{erp['avgMarginPercent']}%",
         "sub": "across entities",
         "tone": _tone_for(erp["avgMarginPercent"], warn=25, danger=15, higher_is_bad=False)},
        {"label": "Customers", "value": f"{crm['total']:,}",
         "sub": f"{crm['atRiskCount']} at risk",
         "tone": "warning" if crm["atRiskCount"] else "positive"},
        {"label": "Lifetime value", "value": assistant.fmt_egp(crm["totalLifetimeValue"]),
         "sub": f"avg {assistant.fmt_egp(crm['avgLifetimeValue'])}", "tone": "neutral"},
        {"label": "Open / escalated", "value": f"{tk['openOrEscalated']:,}",
         "sub": f"of {tk['total']} tickets",
         "tone": "warning" if tk["openOrEscalated"] else "positive"},
        {"label": "SLA breaches", "value": f"{tk['slaBreachRate']}%",
         "sub": f"{tk['negativeRate']}% negative",
         "tone": _tone_for(tk["slaBreachRate"], warn=10, danger=25)},
    ]


def _actions(s: dict) -> list[dict]:
    crm, erp, tk = s["crm"], s["erp"], s["tickets"]
    actions: list[dict] = []

    # 1) Churn exposure among high-value customers.
    if crm["atRiskCount"] > 0:
        exposure = sum(c["lifetimeValueEgp"] for c in crm.get("atRiskHighValue", []))
        if exposure <= 0:
            exposure = int(crm["atRiskCount"] * crm["avgLifetimeValue"])
        sev = "high" if exposure >= 500_000 or crm["atRiskCount"] >= 10 else "medium"
        actions.append({
            "id": "retain-at-risk",
            "title": "Retain at-risk high-value customers",
            "severity": sev,
            "metric": f"{crm['atRiskCount']} at risk · {assistant.fmt_egp(exposure)} LTV exposure",
            "rationale": "These customers show churn signals; proactive retention protects recurring revenue.",
            "suggestedPrompt": "Create a 7-day retention plan for our at-risk high-value customers.",
            "sources": ["CRM Demo Dataset"],
        })

    # 2) SLA breaches / service backlog.
    if tk["slaBreachRate"] >= 5 or tk["openOrEscalated"] > 0:
        sev = "high" if tk["slaBreachRate"] >= 20 else "medium" if tk["slaBreachRate"] >= 10 else "low"
        actions.append({
            "id": "sla-breaches",
            "title": "Reduce SLA breaches and clear the backlog",
            "severity": sev,
            "metric": f"{tk['slaBreachRate']}% breaching · {tk['openOrEscalated']} open/escalated",
            "rationale": "SLA breaches drive churn and penalties; prioritising the backlog restores service levels.",
            "suggestedPrompt": "How can we reduce SLA breaches this week? Prioritise by impact.",
            "sources": ["Ticketing Demo Dataset"],
        })

    # 3) Margin erosion on the weakest entity.
    low = (erp.get("lowestMargin") or [])
    if low and low[0]["marginPercent"] < 25:
        e = low[0]
        sev = "high" if e["marginPercent"] < 10 else "medium"
        actions.append({
            "id": "margin-erosion",
            "title": f"Address margin erosion in {e['name']}",
            "severity": sev,
            "metric": f"{e['name']} at {e['marginPercent']}% margin",
            "rationale": "This entity drags overall profitability; pricing or cost action recovers margin.",
            "suggestedPrompt": f"Why is the margin low for {e['name']} and what actions improve it?",
            "sources": ["ERP Demo Dataset"],
        })

    # 4) Revenue at risk — high revenue + poor sentiment (cross-source).
    hr = (s.get("highRevenuePoorSentiment") or [])
    if hr:
        e = hr[0]
        rev = e.get("revenueEgp")
        actions.append({
            "id": "revenue-at-risk",
            "title": f"Protect revenue at {e['entity']}",
            "severity": "high",
            "metric": (f"{assistant.fmt_egp(rev)} revenue · " if rev else "")
                      + f"{e['negative']} negative tickets",
            "rationale": "A high-revenue area with poor sentiment is the clearest revenue-at-risk signal.",
            "suggestedPrompt": f"What is driving poor sentiment at {e['entity']} and how do we protect that revenue?",
            "sources": ["ERP Demo Dataset", "Ticketing Demo Dataset"],
        })

    # 5) Complaint hotspot.
    cbe = (s.get("complaintsByEntity") or [])
    if cbe and cbe[0]["negative"] > 0 and not any(a["id"] == "revenue-at-risk" for a in actions):
        e = cbe[0]
        actions.append({
            "id": "complaint-hotspot",
            "title": f"Investigate complaints for {e['entity']}",
            "severity": "medium",
            "metric": f"{e['negative']} negative tickets",
            "rationale": "Concentrated complaints point to a fixable root cause.",
            "suggestedPrompt": f"What's driving complaints for {e['entity']}?",
            "sources": ["Ticketing Demo Dataset"],
        })

    actions.sort(key=lambda a: _SEVERITY_RANK.get(a["severity"], 0), reverse=True)
    return actions[:5]


def _fallback_narrative(company: str, role: str, s: dict) -> str:
    crm, erp, tk = s["crm"], s["erp"], s["tickets"]
    return (
        f"{company} is running {assistant.fmt_egp(erp['totalRevenueEgp'])} in revenue at "
        f"{erp['avgMarginPercent']}% average margin across {erp['total']} entities. "
        f"{crm['total']:,} customers are tracked, with {crm['atRiskCount']} flagged at risk. "
        f"Support shows {tk['openOrEscalated']} open/escalated tickets and a "
        f"{tk['slaBreachRate']}% SLA-breach rate — the priorities below are ranked by impact."
    )


async def _narrative(company: str, industry_label: str, role: str, s: dict) -> str:
    if not llm.is_enabled():
        return _fallback_narrative(company, role, s)
    context = assistant.build_data_context(company, industry_label, s)
    question = (
        f"Write a concise 3-sentence executive briefing for the {role}. Highlight the "
        "single biggest risk and the biggest opportunity, using only the figures in the "
        "context. Be direct and specific."
    )
    text = await llm.answer(question=question, company=company, context=context)
    return text or _fallback_narrative(company, role, s)


async def build_briefing(project: dict, permissions: set[str], role: str) -> dict:
    """Assemble a role-scoped briefing. Personas without aggregated-data access get
    a public welcome only — never internal KPIs or actions."""
    company = project.get("companyName", "the company")
    industry_label = project.get("industryLabel", "")
    can_see_data = rbac.has_any(permissions, ["read:connectors:aggregated"])

    if not can_see_data:
        summary = project.get("siteSummary") or f"Welcome to {company}."
        return {
            "role": role,
            "company": company,
            "hasData": False,
            "narrative": (
                f"Welcome. As a {role}, you can ask the assistant about {company}'s "
                "services and information. Internal business data is restricted to "
                "authorised finance and executive roles."
            ),
            "siteSummary": summary,
            "kpis": [],
            "actions": [],
            "suggestedQuestions": project.get("suggestedQuestions", [])[:5],
        }

    s = project.get("analytics") or analytics.build_cross_source_summary(project["connectors"])
    narrative = await _narrative(company, industry_label, role, s)
    return {
        "role": role,
        "company": company,
        "hasData": True,
        "narrative": narrative,
        "kpis": _kpis(s),
        "actions": _actions(s),
        "suggestedQuestions": project.get("suggestedQuestions", [])[:5],
    }
