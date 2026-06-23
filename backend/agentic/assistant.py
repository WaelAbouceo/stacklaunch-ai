"""Assistant reasoning: intent classification, governance metadata, and the
templated fallback answers.

Ported from the former frontend services/assistantService.ts. The LLM (llm.py)
produces the natural-language answer when available; this module always produces
the governance metadata (sources, computedFrom, guardrail notes, observability
deltas, audit events) and the deterministic fallback text used when no LLM is
configured or the model call fails.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from core import config
from data.industries import INDUSTRIES

STOPWORDS = {
    "the", "a", "an", "is", "are", "do", "does", "did", "what", "how", "where",
    "when", "who", "why", "of", "to", "for", "and", "or", "in", "on", "at", "your",
    "you", "we", "me", "my", "can", "could", "with", "this", "that", "about", "have",
    "has", "tell", "please", "any", "there", "their", "they", "it", "its",
}

def fmt_egp(n: int) -> str:
    return f"EGP {n:,}"


def _top_list(items: list[dict], n: int = 5) -> str:
    return "\n".join(
        f"  {i + 1}. {it['label']} — {it['count']} ({it['percent']}%)"
        for i, it in enumerate(items[:n])
    )


def _tickets_this_week(tickets: list[dict]) -> list[dict]:
    return [
        t for t in tickets
        if datetime.fromisoformat(t["createdAt"]).replace(tzinfo=timezone.utc).timestamp() >= config.week_ago_ts()
    ]


def retrieve_knowledge(pages: list[dict], question: str) -> list[dict]:
    terms = [
        t for t in re.findall(r"[a-z0-9]+", question.lower())
        if len(t) > 2 and t not in STOPWORDS
    ]
    hits = []
    for p in pages:
        hay = f"{p.get('title','')} {' '.join(p.get('topics',[]))} {p.get('summary','')} {p.get('content','')}".lower()
        score = sum(hay.count(t) for t in terms)
        snippet = (p.get("summary") or p.get("content") or "")[:320].strip()
        hits.append({"title": p.get("title", ""), "url": p.get("url", ""), "snippet": snippet, "score": score})
    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits


_INTENTS = [
    ("about", r"(what does|about|who are you|company do|business)"),
    ("action_plan", r"(action plan|improvement plan|7-day|seven day|improve|plan to)"),
    ("complaint_rate_entity",
     r"(highest complaint|complaint rate|most complaints|worst-performing|worst performing)"
     r"|(which (route|branch|product|clinic|department|project|property|policy|plan|program))"),
    ("high_rev_poor_sentiment", r"(high revenue|poor sentiment|revenue but)"),
    ("churn", r"(churn|at risk|at-risk|drop ?off|drop out|unhappy)"),
    ("segments_active", r"(segment|customer base|most active|valuable)"),
    ("operational_attention", r"(operational area|needs attention|inventory|margin|utilization|operations)"),
    ("complaints_revenue", r"(relationship between|complaints and revenue|correlation)"),
    ("kyc", r"(kyc)"),
    ("returns", r"(return|refund reasons|reasons for return)"),
    ("top_issues", None),  # special compound test handled below
    ("out_of_scope", r"(weather|stock price|joke|recipe|football|who won)"),
]


def classify(question: str) -> str:
    q = question.lower()
    for intent_id, pattern in _INTENTS:
        if intent_id == "top_issues":
            if re.search(r"(top|main|biggest|common)", q) and re.search(
                r"(issue|complaint|ticket|problem|category|categories)", q
            ):
                return "top_issues"
            continue
        if pattern and re.search(pattern, q):
            return intent_id
    return "knowledge"


def build_data_context(company: str, industry_label: str, s: dict) -> str:
    lines = [f"Company: {company} — {industry_label}."]
    lines.append(
        f"CRM: {s['crm']['total']} customers; segments "
        + ", ".join(f"{x['label']} {x['percent']}%" for x in s["crm"]["bySegment"][:4])
        + f"; {s['crm']['atRiskCount']} at-risk; avg LTV {fmt_egp(s['crm']['avgLifetimeValue'])}."
    )
    lines.append(
        f"ERP: total revenue {fmt_egp(s['erp']['totalRevenueEgp'])}; "
        f"avg margin {s['erp']['avgMarginPercent']}%; lowest-margin "
        + ", ".join(f"{e['name']} {e['marginPercent']}%" for e in s["erp"]["lowestMargin"][:3])
        + "."
    )
    lines.append(
        f"Tickets: {s['tickets']['total']}; top categories "
        + ", ".join(f"{c['label']} {c['percent']}%" for c in s["tickets"]["byCategory"][:4])
        + f"; {s['tickets']['negativeRate']}% negative; {s['tickets']['slaBreachRate']}% SLA breach; "
        f"{s['tickets']['openOrEscalated']} open/escalated."
    )
    if s["complaintsByEntity"]:
        lines.append(
            "Most-complained entities: "
            + ", ".join(f"{e['entity']} ({e['negative']} negative)" for e in s["complaintsByEntity"][:3])
            + "."
        )
    return "\n".join(lines)


_PII_NOTE = (
    "PII masking active — individual customers are referenced by ID and segment only, "
    "never by name, email, or phone."
)


def answer_question(project: dict, question: str, summary: dict) -> dict:
    """Return the AssistantResult (governance metadata + fallback content)."""
    intent = classify(question)
    company = project["companyName"]
    config = INDUSTRIES.get(project["industry"], INDUSTRIES["generic_services"])
    tickets_recs = project["connectors"]["ticketing"]["records"]
    kb = project["knowledgeBase"]

    obs = {"totalAssistantAnswers": 1, "connectorQueries": 1}
    audit = ["assistant_answered", "connector_query_executed"]

    if intent == "out_of_scope":
        return {
            "content": (
                f"That question is outside the scope of {company}'s governed data sources. "
                "I can answer questions about the website knowledge base, customers (CRM), "
                "operations (ERP), and support tickets."
            ),
            "sources": [],
            "computedFrom": [],
            "guardrailNote": "Out-of-scope refusal guardrail applied.",
            "observabilityDelta": {"totalAssistantAnswers": 1, "guardrailBlocks": 1},
            "auditTypes": ["assistant_answered", "guardrail_triggered"],
        }

    if intent == "about":
        real = (project.get("siteSummary") or "").strip()
        page_titles = ", ".join(p["title"] for p in kb["pages"][:5])
        head = (
            f"From {company}'s website: “{real}”\n\n" if real
            else f"{company} is {config['business_description']}.\n\n"
        )
        return {
            "content": head + (
                f"Based on the {kb['pagesIndexed']} pages we indexed from {project['websiteUrl']}, "
                f"key areas include: {page_titles}."
            ),
            "sources": ["Website Knowledge"],
            "computedFrom": [f"{kb['pagesIndexed']} indexed pages", "site description"],
            "observabilityDelta": {"totalAssistantAnswers": 1, "knowledgeQueries": 1},
            "auditTypes": ["assistant_answered", "knowledge_base_built"],
        }

    if intent == "knowledge":
        hits = [h for h in retrieve_knowledge(kb["pages"], question) if h["score"] > 0][:3]
        if not hits:
            titles = ", ".join(p["title"] for p in kb["pages"][:5])
            pre = f"{project.get('siteSummary')}\n\n" if project.get("siteSummary") else ""
            return {
                "content": pre + (
                    f"I couldn't find a specific page about that on {company}'s website. "
                    f"Pages I indexed include: {titles}."
                ),
                "sources": ["Website Knowledge"],
                "computedFrom": [f"{kb['pagesIndexed']} indexed pages"],
                "observabilityDelta": {"totalAssistantAnswers": 1, "knowledgeQueries": 1},
                "auditTypes": ["assistant_answered", "knowledge_base_built"],
            }
        body = "\n\n".join(f"• {h['title']}\n  {h['snippet']}\n  {h['url']}" for h in hits)
        return {
            "content": f"Here's what {company}'s website says, from the pages we indexed:\n\n{body}",
            "sources": ["Website Knowledge"],
            "computedFrom": [h["title"] for h in hits],
            "observabilityDelta": {"totalAssistantAnswers": 1, "knowledgeQueries": 1},
            "auditTypes": ["assistant_answered", "knowledge_base_built"],
        }

    t = summary["tickets"]
    crm = summary["crm"]
    erp = summary["erp"]

    if intent == "top_issues":
        from data.analytics import summarize_tickets
        recent = _tickets_this_week(tickets_recs)
        use_recent = bool(re.search(r"this week|recently|recent", question.lower())) and recent
        s = summarize_tickets(recent) if use_recent else t
        return {
            "content": (
                f"Top support issues{' this week' if use_recent else ''} for {company} "
                f"({s['total']} tickets analyzed):\n{_top_list(s['byCategory'])}\n\n"
                f"Sentiment: {t['negativeRate']}% negative. "
                f"SLA: {t['slaBreachRate']}% breached, {t['openOrEscalated']} open/escalated."
            ),
            "sources": ["Ticketing Demo Dataset"],
            "computedFrom": ["ticket category counts", "sentiment breakdown", "SLA status"],
            "observabilityDelta": {**obs, "ticketingQueries": 1},
            "auditTypes": audit,
        }

    if intent == "segments_active":
        return {
            "content": (
                f"Customer segments for {company} ({crm['total']} customers):\n"
                f"{_top_list(crm['bySegment'])}\n\n"
                f"Status mix: " + ", ".join(f"{x['label']} {x['percent']}%" for x in crm["byStatus"]) + ".\n"
                f"Average lifetime value: {fmt_egp(crm['avgLifetimeValue'])}."
            ),
            "sources": ["CRM Demo Dataset"],
            "computedFrom": ["CRM customers by segment", "CRM customers by status", "avg lifetime value"],
            "guardrailNote": _PII_NOTE,
            "observabilityDelta": {**obs, "crmQueries": 1, "piiMaskingEvents": 1},
            "auditTypes": [*audit, "pii_masking_applied"],
        }

    if intent == "churn":
        listing = "\n".join(
            f"  {i + 1}. {c['customerId']} — {c['segment']}, {c['city']} (LTV {fmt_egp(c['lifetimeValueEgp'])})"
            for i, c in enumerate(crm["atRiskHighValue"])
        )
        return {
            "content": (
                f"{crm['atRiskCount']} customers are flagged \"at risk\" for {company}. "
                f"Highest-value at-risk customers (PII masked):\n{listing}\n\n"
                "These are good candidates for proactive retention outreach."
            ),
            "sources": ["CRM Demo Dataset", "Ticketing Demo Dataset"],
            "computedFrom": ["CRM at-risk customers", "lifetime value ranking"],
            "guardrailNote": _PII_NOTE,
            "observabilityDelta": {**obs, "crmQueries": 1, "piiMaskingEvents": 1, "crossSourceAnswers": 1},
            "auditTypes": [*audit, "pii_masking_applied", "cross_source_insight_generated"],
        }

    if intent == "complaint_rate_entity":
        top = summary["complaintsByEntity"][:5]
        if not top:
            return {
                "content": "No operational entities are linked to tickets in this dataset.",
                "sources": ["Ticketing Demo Dataset"],
                "computedFrom": ["ticket-to-entity join"],
                "observabilityDelta": {**obs, "ticketingQueries": 1},
                "auditTypes": audit,
            }
        lines = "\n".join(
            f"  {i + 1}. {e['entity']} — {e['negative']} negative of {e['complaints']} tickets "
            f"({e['complaintRate']}% negative"
            + (f", revenue {fmt_egp(e['revenueEgp'])}" if e["revenueEgp"] else "") + ")"
            for i, e in enumerate(top)
        )
        return {
            "content": (
                f"Entities with the highest complaint volume for {company}:\n{lines}\n\n"
                f"\"{top[0]['entity']}\" has the most negative tickets and should be prioritized."
            ),
            "sources": ["Ticketing Demo Dataset", "ERP Demo Dataset"],
            "computedFrom": ["complaints joined to ERP entities", "negative sentiment rate"],
            "observabilityDelta": {**obs, "ticketingQueries": 1, "erpQueries": 1, "crossSourceAnswers": 1},
            "auditTypes": [*audit, "cross_source_insight_generated"],
        }

    if intent == "high_rev_poor_sentiment":
        listing = "\n".join(
            f"  {i + 1}. {e['entity']} — revenue {fmt_egp(e['revenueEgp'] or 0)}, "
            f"{e['negative']} negative tickets ({e['complaintRate']}% negative)"
            for i, e in enumerate(summary["highRevenuePoorSentiment"])
        )
        return {
            "content": (
                f"High-revenue entities with poor sentiment for {company} (protect this revenue):\n{listing}\n\n"
                "These combine strong revenue with customer dissatisfaction — the highest-priority fixes."
            ),
            "sources": ["ERP Demo Dataset", "Ticketing Demo Dataset"],
            "computedFrom": ["ERP revenue", "ticket sentiment by entity", "cross-source ranking"],
            "observabilityDelta": {**obs, "erpQueries": 1, "ticketingQueries": 1, "crossSourceAnswers": 1},
            "auditTypes": [*audit, "cross_source_insight_generated"],
        }

    if intent == "operational_attention":
        low_margin = ", ".join(f"{e['name']} ({e['marginPercent']}% margin)" for e in erp["lowestMargin"][:3])
        low_util = ", ".join(f"{e['name']} ({e['utilizationPercent']}% utilization)" for e in erp["lowestUtilization"][:3])
        return {
            "content": (
                f"Operational attention areas for {company}:\n"
                f"- Lowest margin: {low_margin}\n"
                f"- Lowest utilization: {low_util}\n"
                f"- Avg margin across operations: {erp['avgMarginPercent']}%\n"
                f"- Support pressure: {t['openOrEscalated']} open/escalated tickets, {t['slaBreachRate']}% SLA breach.\n\n"
                "Focus first where low margin overlaps with high complaint volume."
            ),
            "sources": ["ERP Demo Dataset", "Ticketing Demo Dataset"],
            "computedFrom": ["ERP lowest-margin entities", "ERP lowest utilization", "ticket SLA status"],
            "observabilityDelta": {**obs, "erpQueries": 1, "ticketingQueries": 1, "crossSourceAnswers": 1},
            "auditTypes": [*audit, "cross_source_insight_generated"],
        }

    if intent == "complaints_revenue":
        top = summary["highRevenuePoorSentiment"][:3]
        lines = "\n".join(
            f"  • {e['entity']}: {fmt_egp(e['revenueEgp'] or 0)} revenue, {e['negative']} negative tickets"
            for e in top
        )
        return {
            "content": (
                f"Relationship between complaints and revenue at {company}:\n"
                f"Total revenue {fmt_egp(erp['totalRevenueEgp'])}, {t['negativeRate']}% of tickets are negative.\n"
                f"Entities where revenue and complaints both concentrate:\n{lines}\n\n"
                "Dissatisfaction is concentrated in a few high-revenue entities, so targeted fixes protect the most revenue."
            ),
            "sources": ["ERP Demo Dataset", "Ticketing Demo Dataset"],
            "computedFrom": ["ERP revenue totals", "ticket sentiment", "entity-level join"],
            "observabilityDelta": {**obs, "erpQueries": 1, "ticketingQueries": 1, "crossSourceAnswers": 1},
            "auditTypes": [*audit, "cross_source_insight_generated"],
        }

    if intent == "kyc":
        kyc = next((c for c in t["byCategory"] if re.search(r"kyc", c["label"], re.I)), None)
        content = (
            f"KYC-related support for {company}: {kyc['count']} tickets ({kyc['percent']}% of all tickets). "
            f"Across all categories, {t['openOrEscalated']} tickets are open/escalated and "
            f"{t['slaBreachRate']}% breach SLA. Recommend a dedicated KYC fast-track to clear the backlog."
            if kyc else
            f"No KYC-specific tickets were found in this dataset. Top categories instead:\n{_top_list(t['byCategory'], 3)}"
        )
        return {
            "content": content,
            "sources": ["Ticketing Demo Dataset"],
            "computedFrom": ["ticket category counts", "SLA status"],
            "observabilityDelta": {**obs, "ticketingQueries": 1},
            "auditTypes": audit,
        }

    if intent == "returns":
        ret = next((c for c in t["byCategory"] if re.search(r"return|refund", c["label"], re.I)), None)
        not_within = sum(s["count"] for s in t["bySlaStatus"] if s["label"] != "within_sla")
        return {
            "content": (
                f"Top return/refund signals for {company}:\n"
                + (f"- {ret['label']}: {ret['count']} tickets ({ret['percent']}%)\n" if ret else "")
                + f"- Overall negative sentiment: {t['negativeRate']}%\n"
                + f"- SLA at risk/breached: {not_within} tickets\n\n"
                + "Most returns trace back to the leading categories: "
                + ", ".join(c["label"] for c in t["byCategory"][:3]) + "."
            ),
            "sources": ["Ticketing Demo Dataset"],
            "computedFrom": ["ticket category counts", "sentiment", "SLA status"],
            "observabilityDelta": {**obs, "ticketingQueries": 1},
            "auditTypes": audit,
        }

    if intent == "action_plan":
        top_cat = t["topCategory"]
        worst = summary["complaintsByEntity"][0] if summary["complaintsByEntity"] else None
        low_margin = erp["lowestMargin"][0] if erp["lowestMargin"] else None
        top_label = top_cat["label"] if top_cat else "top issues"
        top_count = top_cat["count"] if top_cat else 0
        plan = [
            f"Days 1-2 — Triage: clear the {t['openOrEscalated']} open/escalated tickets, "
            f"prioritizing \"{top_label}\" ({top_count} tickets) and any SLA breaches ({t['slaBreachRate']}%).",
            (f"Days 2-3 — Root cause: investigate \"{worst['entity']}\" ({worst['negative']} negative tickets"
             + (f", {fmt_egp(worst['revenueEgp'])} revenue" if worst and worst["revenueEgp"] else "") + ").")
            if worst else "Days 2-3 — Root cause: investigate the leading complaint category.",
            f"Days 3-4 — Retention: proactively contact the {crm['atRiskCount']} at-risk customers "
            "(highest LTV first) via their preferred channel.",
            (f"Days 4-5 — Operations: review \"{low_margin['name']}\" ({low_margin['marginPercent']}% margin) "
             "and other low-margin areas for cost/quality issues.")
            if low_margin else "Days 4-5 — Operations: review lowest-margin areas.",
            f"Days 5-6 — Knowledge: update website policies and FAQs that drive the most \"{top_label}\" "
            "contacts to deflect repeat tickets.",
            f"Day 7 — Review: measure ticket volume, negative sentiment (now {t['negativeRate']}%), "
            "and SLA breach rate against baseline.",
        ]
        return {
            "content": (
                f"7-day customer experience action plan for {company}:\n\n"
                + "\n".join(f"• {p}" for p in plan)
                + "\n\nThis plan combines website policies, CRM at-risk segments, ERP operations, and ticketing trends."
            ),
            "sources": ["Website Knowledge", "CRM Demo Dataset", "ERP Demo Dataset", "Ticketing Demo Dataset"],
            "computedFrom": [
                "ticket category + SLA", "complaints by entity",
                "CRM at-risk customers", "ERP lowest-margin entities",
            ],
            "guardrailNote": _PII_NOTE,
            "observabilityDelta": {
                **obs, "knowledgeQueries": 1, "crmQueries": 1, "erpQueries": 1,
                "ticketingQueries": 1, "crossSourceAnswers": 1, "piiMaskingEvents": 1,
            },
            "auditTypes": [*audit, "cross_source_insight_generated", "pii_masking_applied"],
        }

    return {
        "content": f"Here is a summary of {company}'s support tickets:\n{_top_list(t['byCategory'])}",
        "sources": ["Ticketing Demo Dataset"],
        "computedFrom": ["ticket category counts"],
        "observabilityDelta": {**obs, "ticketingQueries": 1},
        "auditTypes": audit,
    }
