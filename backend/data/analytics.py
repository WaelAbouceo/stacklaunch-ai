"""Connector analytics + cross-source summaries.

Ported from the former frontend services/connectorQueryService.ts. Output keys
are camelCase to match the shapes the frontend renders. This is the ONLY view of
the internal data exposed to the dashboard and the assistant — never raw records
in the assistant path.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from core import config


def _round1(x: float) -> float:
    return round(x * 10) / 10


def count_by(items: list[dict], key: str) -> list[dict]:
    counts: dict[str, int] = defaultdict(int)
    for it in items:
        counts[it[key]] += 1
    total = len(items) or 1
    out = [
        {"label": label, "count": c, "percent": _round1(c / total * 100)}
        for label, c in counts.items()
    ]
    out.sort(key=lambda x: x["count"], reverse=True)
    return out


def summarize_tickets(tickets: list[dict]) -> dict:
    by_category = count_by(tickets, "category")
    negative = sum(1 for t in tickets if t["sentiment"] == "negative")
    breached = sum(1 for t in tickets if t["slaStatus"] == "breached")
    open_or_esc = sum(1 for t in tickets if t["status"] in ("Open", "Escalated"))
    recent = sum(
        1 for t in tickets
        if datetime.fromisoformat(t["createdAt"]).replace(tzinfo=timezone.utc).timestamp() >= config.week_ago_ts()
    )
    n = len(tickets) or 1
    return {
        "total": len(tickets),
        "byCategory": by_category,
        "bySentiment": count_by(tickets, "sentiment"),
        "bySlaStatus": count_by(tickets, "slaStatus"),
        "byPriority": count_by(tickets, "priority"),
        "byStatus": count_by(tickets, "status"),
        "byChannel": count_by(tickets, "channel"),
        "openOrEscalated": open_or_esc,
        "negativeRate": _round1(negative / n * 100),
        "slaBreachRate": _round1(breached / n * 100),
        "recentWeekCount": recent,
        "topCategory": by_category[0] if by_category else None,
    }


def summarize_crm(crm: list[dict]) -> dict:
    at_risk = [c for c in crm if c["status"] == "at_risk"]
    at_risk_hv = sorted(at_risk, key=lambda c: c["lifetimeValueEgp"], reverse=True)[:5]
    total_ltv = sum(c["lifetimeValueEgp"] for c in crm)
    n = len(crm) or 1
    return {
        "total": len(crm),
        "bySegment": count_by(crm, "segment"),
        "byStatus": count_by(crm, "status"),
        "byCity": count_by(crm, "city"),
        "byChannel": count_by(crm, "preferredChannel"),
        "atRiskCount": len(at_risk),
        "atRiskHighValue": [
            {
                "customerId": c["customerId"],
                "segment": c["segment"],
                "city": c["city"],
                "lifetimeValueEgp": c["lifetimeValueEgp"],
            }
            for c in at_risk_hv
        ],
        "avgLifetimeValue": round(total_ltv / n),
        "totalLifetimeValue": total_ltv,
    }


def _entity_summary(e: dict) -> dict:
    return {
        "name": e["name"],
        "entityType": e["entityType"],
        "revenueEgp": e["revenueEgp"],
        "marginPercent": e["marginPercent"],
        "utilizationPercent": e["utilizationPercent"],
    }


def summarize_erp(erp: list[dict]) -> dict:
    total_revenue = sum(e["revenueEgp"] for e in erp)
    total_cost = sum(e["costEgp"] for e in erp)
    avg_margin = sum(e["marginPercent"] for e in erp) / (len(erp) or 1)
    return {
        "total": len(erp),
        "byEntityType": count_by(erp, "entityType"),
        "topRevenue": [_entity_summary(e) for e in sorted(erp, key=lambda x: x["revenueEgp"], reverse=True)[:5]],
        "lowestMargin": [_entity_summary(e) for e in sorted(erp, key=lambda x: x["marginPercent"])[:5]],
        "lowestUtilization": [_entity_summary(e) for e in sorted(erp, key=lambda x: x["utilizationPercent"])[:5]],
        "totalRevenueEgp": total_revenue,
        "totalCostEgp": total_cost,
        "avgMarginPercent": _round1(avg_margin),
    }


def complaints_by_entity(tickets: list[dict], erp: list[dict]) -> list[dict]:
    agg: dict[str, dict] = {}
    for t in tickets:
        ent = t.get("linkedEntity")
        if not ent:
            continue
        cur = agg.setdefault(ent, {"complaints": 0, "negative": 0})
        cur["complaints"] += 1
        if t["sentiment"] == "negative":
            cur["negative"] += 1
    erp_by_name = {e["name"]: e for e in erp}
    out = []
    for entity, v in agg.items():
        erp_rec = erp_by_name.get(entity)
        out.append({
            "entity": entity,
            "complaints": v["complaints"],
            "negative": v["negative"],
            "revenueEgp": erp_rec["revenueEgp"] if erp_rec else None,
            "marginPercent": erp_rec["marginPercent"] if erp_rec else None,
            "complaintRate": _round1(v["negative"] / (v["complaints"] or 1) * 100),
        })
    out.sort(key=lambda x: x["negative"], reverse=True)
    return out


def build_cross_source_summary(connectors: dict) -> dict:
    tickets = connectors["ticketing"]["records"]
    crm = connectors["crm"]["records"]
    erp = connectors["erp"]["records"]
    by_entity = complaints_by_entity(tickets, erp)
    high_rev_poor = sorted(
        [e for e in by_entity if e["revenueEgp"] is not None and e["negative"] > 0],
        key=lambda e: (e["revenueEgp"] or 0) * (e["negative"] + 1),
        reverse=True,
    )[:5]
    return {
        "tickets": summarize_tickets(tickets),
        "crm": summarize_crm(crm),
        "erp": summarize_erp(erp),
        "complaintsByEntity": by_entity,
        "highRevenuePoorSentiment": high_rev_poor,
    }
