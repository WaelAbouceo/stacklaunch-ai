"""Generate the (synthetic) internal CRM / ERP / ticketing datasets.

Ported from the former frontend services/mockDataGeneratorService.ts. These
represent private internal systems we can't crawl, so they remain generated.
"""

from __future__ import annotations

from datetime import timedelta

from core import config
from data.industries import INDUSTRIES, FIRST_NAMES, LAST_NAMES
from core.rng import SeededRandom

CHANNELS = ["WhatsApp", "Phone", "Email", "Web"]
PRIORITIES = ["Low", "Medium", "High", "Critical"]
STATUSES = ["Open", "Pending", "Resolved", "Escalated"]
SENTIMENTS = ["positive", "neutral", "negative"]
SLA = ["within_sla", "at_risk", "breached"]

_LINKABLE_TYPES = {
    "route", "branch", "product", "clinic", "department", "project",
    "property", "policy", "plan", "program", "service",
}

# Entity types that are metrics/KPIs rather than revenue-bearing lines. They're
# excluded from the ERP "revenue & margin" ledger so demo numbers stay coherent.
_NON_REVENUE_TYPES = {"operational_kpi"}


def _pad(n: int, width: int) -> str:
    return str(n).rjust(width, "0")


def _iso_date_within(rng: SeededRandom, max_days_ago: int) -> str:
    offset = rng.randint(0, max_days_ago)
    return (config.now_utc() - timedelta(days=offset)).date().isoformat()


def _profile_list(profile: "dict | None", key: str) -> "list | None":
    """Return a non-empty list from the data profile, else None (use defaults)."""
    if not profile:
        return None
    value = profile.get(key)
    return value if isinstance(value, list) and value else None


def _profile_range(
    profile: "dict | None", key: str, default: tuple[int, int]
) -> tuple[int, int]:
    """Pull a numeric [min, max] range from profile['scale'], else the default."""
    if profile:
        scale = profile.get("scale")
        if isinstance(scale, dict):
            rng_val = scale.get(key)
            if (
                isinstance(rng_val, (list, tuple))
                and len(rng_val) == 2
                and rng_val[0] < rng_val[1]
            ):
                return int(rng_val[0]), int(rng_val[1])
    return default


def generate_crm(
    industry: str, seed: str, count: int = 250, profile: "dict | None" = None
) -> list[dict]:
    cfg = INDUSTRIES[industry]
    rng = SeededRandom(f"{seed}:crm")
    # Ground the vocabulary in the real site when a profile is available.
    segments = _profile_list(profile, "segments") or cfg["crm_segments"]
    cities = _profile_list(profile, "cities") or cfg["cities"]
    ltv_lo, ltv_hi = _profile_range(profile, "ltv", (500, 50000))
    records: list[dict] = []
    for i in range(1, count + 1):
        first = rng.pick(FIRST_NAMES)
        last = rng.pick(LAST_NAMES)
        status = rng.weighted(["active", "at_risk", "inactive"], [0.62, 0.23, 0.15])
        records.append({
            "customerId": f"CUST-{_pad(i, 3)}",
            "name": f"{first} {last}",
            "segment": rng.pick(segments),
            "city": rng.pick(cities),
            "email": f"{first}.{last}".lower() + "@example.com",
            "phone": f"+20{rng.randint(10, 12)}{rng.randint(10000000, 99999999)}",
            "lifetimeValueEgp": rng.randint(ltv_lo, ltv_hi),
            "lastInteraction": _iso_date_within(rng, 120),
            "preferredChannel": rng.pick(CHANNELS),
            "status": status,
        })
    return records


def generate_erp(
    industry: str, seed: str, count: int = 80, profile: "dict | None" = None
) -> list[dict]:
    cfg = INDUSTRIES[industry]
    rng = SeededRandom(f"{seed}:erp")
    pool = []
    # Real products/services/locations from the site take priority over templates.
    profile_products = _profile_list(profile, "products")
    if profile_products:
        for e in profile_products:
            if isinstance(e, dict) and e.get("name"):
                pool.append({
                    "entity_type": str(e.get("entity_type") or "product"),
                    "name": str(e["name"]),
                })
    if not pool:
        for e in cfg["erp_entities"]:
            # KPIs are metrics, not revenue lines — including them produces nonsense
            # like "margin erosion on Churn Rate", so keep them out of the ERP ledger.
            if e["entity_type"] in _NON_REVENUE_TYPES:
                continue
            for n in e["names"]:
                pool.append({"entity_type": e["entity_type"], "name": n})

    rev_lo, rev_hi = _profile_range(profile, "monthly_revenue", (40000, 800000))
    records: list[dict] = []
    for i in range(1, count + 1):
        base = pool[(i - 1) % len(pool)]
        variant = (i - 1) // len(pool)
        name = base["name"] if variant == 0 else f"{base['name']} ({variant + 1})"
        revenue = rng.randint(rev_lo, rev_hi)
        margin = rng.randint(-5, 45)
        cost = round(revenue * (1 - margin / 100))
        records.append({
            "recordId": f"ERP-{_pad(i, 3)}",
            "entityType": base["entity_type"],
            "name": name,
            "revenueEgp": revenue,
            "costEgp": cost,
            "marginPercent": margin,
            "utilizationPercent": rng.randint(35, 98),
            "period": config.now_utc().strftime("%B %Y"),
        })
    return records


_SUMMARY_TEMPLATES = {
    "default": [
        "Customer raised a {c} issue{t}.",
        "Follow-up required on {c}{t}.",
        "Customer reported a problem with {c}{t}.",
    ],
    "Refund": [
        "Customer requested a refund after trip cancellation{t}.",
        "Refund not processed within expected time{t}.",
    ],
    "Delay": [
        "Customer complained about a significant delay{t}.",
        "Departure was delayed and customer missed a connection{t}.",
    ],
    "Return": [
        "Customer wants to return an item{t}.",
        "Return pickup was not collected on time{t}.",
    ],
    "Delivery Delay": [
        "Order delivery is late{t}.",
        "Customer waiting beyond promised delivery date{t}.",
    ],
    "Card Issue": [
        "Card was declined unexpectedly{t}.",
        "Customer reported a blocked card{t}.",
    ],
    "Appointment": [
        "Customer wants to reschedule an appointment{t}.",
        "Appointment slot unavailable{t}.",
    ],
    "Network Issue": [
        "Customer reports poor network coverage{t}.",
        "Frequent disconnections reported{t}.",
    ],
}


def _summary_for(category: str, entity: "str | None", rng: SeededRandom) -> str:
    target = f" related to {entity}" if entity else ""
    templates = _SUMMARY_TEMPLATES.get(category, _SUMMARY_TEMPLATES["default"])
    return rng.pick(templates).format(c=category.lower(), t=target)


def generate_ticketing(
    industry: str,
    seed: str,
    crm: list[dict],
    erp: list[dict],
    count: int = 120,
    profile: "dict | None" = None,
) -> list[dict]:
    cfg = INDUSTRIES[industry]
    rng = SeededRandom(f"{seed}:tickets")
    categories = _profile_list(profile, "ticket_categories") or cfg["ticket_categories"]
    category_weights = [3 if idx < 2 else 2 if idx < 4 else 1 for idx in range(len(categories))]
    linkable = [e["name"] for e in erp if e["entityType"] in _LINKABLE_TYPES]
    # When ERP entities come from a real-site profile their types may not be in the
    # default "linkable" set — fall back to linking against every ERP record so
    # tickets still reference the company's real products/services.
    if not linkable:
        linkable = [e["name"] for e in erp]

    records: list[dict] = []
    for i in range(1, count + 1):
        category = rng.weighted(categories, category_weights)
        customer = rng.pick(crm)
        linked = rng.pick(linkable) if linkable else None
        negative_bias = categories.index(category) < 2
        sentiment = rng.weighted(
            SENTIMENTS, [0.1, 0.25, 0.65] if negative_bias else [0.3, 0.35, 0.35]
        )
        priority = rng.weighted(PRIORITIES, [0.3, 0.35, 0.25, 0.1])
        status = rng.weighted(STATUSES, [0.35, 0.25, 0.3, 0.1])
        sla_status = rng.weighted(
            SLA, [0.35, 0.35, 0.3] if sentiment == "negative" else [0.7, 0.2, 0.1]
        )
        records.append({
            "ticketId": f"TCK-{_pad(i, 3)}",
            "customerId": customer["customerId"],
            "category": category,
            "priority": priority,
            "status": status,
            "createdAt": _iso_date_within(rng, 21),
            "channel": rng.pick(CHANNELS),
            "summary": _summary_for(category, linked, rng),
            "sentiment": sentiment,
            "slaStatus": sla_status,
            "linkedEntity": linked,
        })
    return records
