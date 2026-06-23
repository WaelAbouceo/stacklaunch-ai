"""Organisational structure + data-classification model for enterprise RBAC.

Replaces the flat business personas (Customer/Accountant/CFO/CEO) with an org-aware
access model built on three independent axes:

  1. Admin tier (vertical authority):  system > department > group > member, plus
     `external` for users outside the org.
  2. Org scope (horizontal):           which department / group the seat belongs to.
  3. Clearance (data sensitivity):     public < internal < confidential < restricted.

A read is permitted when the principal holds the functional permission AND its
clearance >= the resource classification AND the resource's department is in the
principal's scope (or the principal has cross-scope authority).

The org chart itself is *industry-driven*: each industry has a department/group
template (optionally LLM-pruned to what a scanned site implies — see
`build_org_structure`). This module is pure data + logic; persistence, key minting,
and enforcement live in security.py / rbac.py / tools.py.
"""

from __future__ import annotations

# --- Clearance ladder -----------------------------------------------------
# Ordered low -> high; the index is the numeric level used for comparisons.
CLEARANCE_LEVELS: list[str] = ["public", "internal", "confidential", "restricted"]


def clearance_level(name: str | None) -> int:
    try:
        return CLEARANCE_LEVELS.index((name or "public").lower())
    except ValueError:
        return 0


def clearance_allows(principal_clearance: str | None, resource_classification: str | None) -> bool:
    return clearance_level(principal_clearance) >= clearance_level(resource_classification)


# --- Admin tiers ----------------------------------------------------------
ADMIN_TIERS: list[str] = ["external", "member", "group", "department", "system"]


def tier_rank(tier: str | None) -> int:
    try:
        return ADMIN_TIERS.index((tier or "external").lower())
    except ValueError:
        return 0


# --- Industry org templates ----------------------------------------------
# Each template: departments (name + groups) and a data_domains map binding the
# connector/knowledge sources to an owning department + default classification.
# A generic template backs any industry without a specific one.

_GENERIC = {
    "departments": [
        {"name": "Operations", "groups": ["Service Delivery", "Quality", "Planning"]},
        {"name": "Customer Support", "groups": ["Frontline", "Escalations", "Retention"]},
        {"name": "Finance", "groups": ["Billing", "Accounting", "Procurement"]},
        {"name": "Sales & Marketing", "groups": ["Sales", "Marketing", "Partnerships"]},
        {"name": "Compliance & Risk", "groups": ["Regulatory", "Audit", "Security"]},
    ],
    "data_domains": {
        "crm": {"department": "Sales & Marketing", "classification": "confidential"},
        "erp": {"department": "Finance", "classification": "restricted"},
        "ticketing": {"department": "Customer Support", "classification": "internal"},
        "knowledge": {"department": None, "classification": "public"},
    },
}

ORG_TEMPLATES: dict[str, dict] = {
    "telecom": {
        "departments": [
            {"name": "Network Operations", "groups": ["Core Network", "Field Engineering", "NOC"]},
            {"name": "Customer Care", "groups": ["Call Center", "Retention", "Escalations"]},
            {"name": "Finance", "groups": ["Billing", "Revenue Assurance", "Procurement"]},
            {"name": "Retail & Sales", "groups": ["Stores", "Enterprise Sales", "Digital"]},
            {"name": "Compliance & Risk", "groups": ["Regulatory", "Fraud", "Internal Audit"]},
        ],
        "data_domains": {
            "crm": {"department": "Retail & Sales", "classification": "confidential"},
            "erp": {"department": "Finance", "classification": "restricted"},
            "ticketing": {"department": "Customer Care", "classification": "internal"},
            "knowledge": {"department": None, "classification": "public"},
        },
    },
    "banking": {
        "departments": [
            {"name": "Retail Banking", "groups": ["Branches", "Cards", "Digital Banking"]},
            {"name": "Corporate Banking", "groups": ["SME", "Large Corporates", "Trade Finance"]},
            {"name": "Finance & Treasury", "groups": ["Accounting", "Treasury", "Investor Relations"]},
            {"name": "Customer Service", "groups": ["Call Center", "Complaints", "Onboarding"]},
            {"name": "Compliance & Risk", "groups": ["AML / KYC", "Credit Risk", "Internal Audit"]},
        ],
        "data_domains": {
            "crm": {"department": "Retail Banking", "classification": "confidential"},
            "erp": {"department": "Finance & Treasury", "classification": "restricted"},
            "ticketing": {"department": "Customer Service", "classification": "internal"},
            "knowledge": {"department": None, "classification": "public"},
        },
    },
    "healthcare": {
        "departments": [
            {"name": "Clinical Services", "groups": ["Outpatient", "Inpatient", "Diagnostics"]},
            {"name": "Patient Experience", "groups": ["Front Desk", "Appointments", "Complaints"]},
            {"name": "Finance & Billing", "groups": ["Billing", "Insurance Claims", "Procurement"]},
            {"name": "Pharmacy & Supplies", "groups": ["Pharmacy", "Inventory", "Suppliers"]},
            {"name": "Compliance & Quality", "groups": ["Patient Safety", "Regulatory", "Records"]},
        ],
        "data_domains": {
            "crm": {"department": "Patient Experience", "classification": "restricted"},
            "erp": {"department": "Finance & Billing", "classification": "restricted"},
            "ticketing": {"department": "Patient Experience", "classification": "confidential"},
            "knowledge": {"department": None, "classification": "public"},
        },
    },
    "retail": {
        "departments": [
            {"name": "Merchandising", "groups": ["Buying", "Planning", "Pricing"]},
            {"name": "Store Operations", "groups": ["Stores", "Logistics", "Fulfilment"]},
            {"name": "E-commerce", "groups": ["Web", "App", "Marketplace"]},
            {"name": "Finance", "groups": ["Accounting", "Treasury", "Procurement"]},
            {"name": "Customer Care", "groups": ["Support", "Returns", "Loyalty"]},
        ],
        "data_domains": {
            "crm": {"department": "Customer Care", "classification": "confidential"},
            "erp": {"department": "Finance", "classification": "restricted"},
            "ticketing": {"department": "Customer Care", "classification": "internal"},
            "knowledge": {"department": None, "classification": "public"},
        },
    },
    "insurance": {
        "departments": [
            {"name": "Underwriting", "groups": ["Motor", "Health", "Life & Property"]},
            {"name": "Claims", "groups": ["Intake", "Assessment", "Settlement"]},
            {"name": "Finance & Actuarial", "groups": ["Accounting", "Actuarial", "Reinsurance"]},
            {"name": "Customer Service", "groups": ["Call Center", "Renewals", "Complaints"]},
            {"name": "Compliance & Risk", "groups": ["Regulatory", "Fraud", "Internal Audit"]},
        ],
        "data_domains": {
            "crm": {"department": "Customer Service", "classification": "confidential"},
            "erp": {"department": "Finance & Actuarial", "classification": "restricted"},
            "ticketing": {"department": "Customer Service", "classification": "internal"},
            "knowledge": {"department": None, "classification": "public"},
        },
    },
    "technology": {
        "departments": [
            {"name": "Engineering", "groups": ["Platform", "Frontend", "Infrastructure"]},
            {"name": "Product", "groups": ["Product Management", "Design", "Research"]},
            {"name": "Customer Success", "groups": ["Support", "Onboarding", "Renewals"]},
            {"name": "Finance", "groups": ["Accounting", "Billing", "Procurement"]},
            {"name": "Security & Compliance", "groups": ["AppSec", "GRC", "IT"]},
        ],
        "data_domains": {
            "crm": {"department": "Customer Success", "classification": "confidential"},
            "erp": {"department": "Finance", "classification": "restricted"},
            "ticketing": {"department": "Customer Success", "classification": "internal"},
            "knowledge": {"department": None, "classification": "public"},
        },
    },
}


def _template_for(industry: str) -> dict:
    return ORG_TEMPLATES.get(industry, _GENERIC)


# --- Field-level data classification --------------------------------------
# Within an in-scope connector, individual fields can be more sensitive than the
# connector's baseline. Aggregated counts/categories are always 'internal'; these
# fields require the listed clearance (or higher) to be returned in raw form.
# Anything not listed defaults to 'internal'.
FIELD_SENSITIVITY: dict[str, dict[str, str]] = {
    "crm": {
        "name": "restricted",
        "email": "restricted",
        "phone": "restricted",
        "nationalId": "restricted",
        "lifetimeValue": "confidential",
        "revenue": "confidential",
    },
    "erp": {
        "revenue": "confidential",
        "margin": "confidential",
        "cost": "confidential",
        "profit": "confidential",
    },
    "ticketing": {
        "customerName": "restricted",
        "customerEmail": "restricted",
        "customerId": "confidential",
    },
}


def field_classification(connector: str, field: str) -> str:
    return FIELD_SENSITIVITY.get(connector, {}).get(field, "internal")


def department_in_scope(
    principal_department: str | None,
    admin_tier: str | None,
    owner_department: str | None,
) -> bool:
    """Whether a principal may reach a resource owned by ``owner_department``.

    System admins (and legacy/anonymous principals with no department) have
    cross-department reach; everyone else is confined to their own department.
    Resources with no owning department (e.g. the public knowledge base) are
    always in scope.
    """
    if owner_department is None:
        return True
    if admin_tier == "system":
        return True
    if principal_department is None:
        # Legacy role keys / anonymous full-access principals are not dept-scoped.
        return True
    return principal_department == owner_department


def connector_domain(org: dict | None, connector: str) -> dict:
    """The owning department + baseline classification for a connector."""
    if org and connector in org.get("dataDomains", {}):
        return org["dataDomains"][connector]
    return _GENERIC["data_domains"].get(connector, {"department": None, "classification": "internal"})


def build_org_structure(industry: str, profile: dict | None = None) -> dict:
    """Return the org chart for an industry.

    Deterministic by default (the industry template). ``profile`` is the
    LLM-extracted data profile; a later phase uses it to prune departments to what
    the scanned site actually implies. For now it is accepted for forward-compat.
    """
    template = _template_for(industry)
    departments = [
        {"name": d["name"], "groups": list(d.get("groups", []))}
        for d in template["departments"]
    ]
    return {
        "industry": industry,
        "clearanceLevels": list(CLEARANCE_LEVELS),
        "departments": departments,
        "dataDomains": {k: dict(v) for k, v in template["data_domains"].items()},
    }


# --- Seat access derivation ----------------------------------------------
# Functional permission sets per admin tier. Scope (department/group) and
# clearance further constrain *which* data these permissions can reach; that is
# enforced in rbac.can_access. Here we only set the functional capability + the
# default clearance a tier is granted.
_TIER_ACCESS: dict[str, dict] = {
    "system": {
        "clearance": "restricted",
        "permissions": {"*"},
    },
    "department": {
        "clearance": "restricted",
        "permissions": {
            "use:assistant", "read:knowledge", "read:all",
            "view:audit", "manage:connectors", "manage:keys",
        },
    },
    "group": {
        "clearance": "confidential",
        "permissions": {
            "use:assistant", "read:knowledge",
            "read:connectors:aggregated", "read:ticketing:aggregated",
            "view:audit", "manage:keys",
        },
    },
    "member": {
        "clearance": "internal",
        "permissions": {"use:assistant", "read:knowledge", "read:connectors:aggregated"},
    },
    "external": {
        "clearance": "public",
        "permissions": {"use:assistant", "read:knowledge"},
    },
}


def derive_access(tier: str, department: str | None = None, group: str | None = None) -> dict:
    """Resolve a seat (tier + scope) into its concrete access attributes."""
    base = _TIER_ACCESS.get(tier, _TIER_ACCESS["external"])
    # System and external are org-wide / org-less: ignore any scope passed in.
    if tier in ("system", "external"):
        department, group = None, None
    return {
        "tier": tier,
        "department": department,
        "group": group,
        "clearance": base["clearance"],
        "permissions": set(base["permissions"]),
    }


def seat_label(tier: str, department: str | None = None, group: str | None = None) -> str:
    if tier == "system":
        return "System Administrator"
    if tier == "external":
        return "External User"
    dept = department or "Organisation"
    if tier == "department":
        return f"{dept} · Department Head"
    if tier == "group":
        return f"{dept}{(' / ' + group) if group else ''} · Group Lead"
    return f"{dept} · Staff"


def seats_catalog(org: dict) -> list[dict]:
    """The selectable login seats for an org chart, used by the seat picker.

    A flat catalogue the frontend groups by department: one System Administrator,
    one External User, and per department a Department Head, Group Lead, and Staff
    seat (group chosen client-side from the department's groups when relevant).
    """
    seats: list[dict] = [
        {
            "id": "system",
            "tier": "system",
            "department": None,
            "group": None,
            "label": seat_label("system"),
            "clearance": _TIER_ACCESS["system"]["clearance"],
        }
    ]
    for dept in org.get("departments", []):
        name = dept["name"]
        for tier in ("department", "group", "member"):
            seats.append({
                "id": f"{name}:{tier}",
                "tier": tier,
                "department": name,
                "group": None,
                "label": seat_label(tier, name),
                "clearance": _TIER_ACCESS[tier]["clearance"],
            })
    seats.append({
        "id": "external",
        "tier": "external",
        "department": None,
        "group": None,
        "label": seat_label("external"),
        "clearance": _TIER_ACCESS["external"]["clearance"],
    })
    return seats
