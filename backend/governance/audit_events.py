"""Governance defaults + audit/observability helpers.

Ported from the former frontend services/governanceService.ts and the audit
message helper that used to live in the frontend store.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

_audit_counter = 0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_audit_event(type_: str, message: str, actor: str = "system") -> dict:
    global _audit_counter
    _audit_counter += 1
    return {
        "id": f"AUD-{int(time.time() * 1000)}-{_audit_counter}",
        "type": type_,
        "message": message,
        "actor": actor,
        "timestamp": _now_iso(),
    }


def initial_observability() -> dict:
    return {
        "websiteScans": 0,
        "knowledgeQueries": 0,
        "connectorQueries": 0,
        "crmQueries": 0,
        "erpQueries": 0,
        "ticketingQueries": 0,
        "crossSourceAnswers": 0,
        "piiMaskingEvents": 0,
        "guardrailBlocks": 0,
        "totalAssistantAnswers": 0,
    }


def audit_message_for(type_: str, question: str) -> str:
    q = question if len(question) <= 60 else question[:57] + "..."
    return {
        "assistant_answered": f'Assistant answered: "{q}"',
        "connector_query_executed": f'Connector summaries computed for: "{q}"',
        "cross_source_insight_generated": f'Cross-source insight generated for: "{q}"',
        "pii_masking_applied": f'PII masking applied while answering: "{q}"',
        "guardrail_triggered": f'Guardrail triggered for: "{q}"',
        "knowledge_base_built": f'Knowledge base queried for: "{q}"',
    }.get(type_, f'{type_} for: "{q}"')


def build_audit_events(audit_types: list[str], question: str, actor: str = "assistant") -> list[dict]:
    return [create_audit_event(t, audit_message_for(t, question), actor) for t in audit_types]


DEFAULT_GUARDRAILS = [
    {"id": "g1", "title": "Source-grounded answers",
     "description": "Responses are grounded in the website knowledge base and connector datasets only.",
     "status": "active"},
    {"id": "g2", "title": "No hallucinated business facts",
     "description": "The assistant never invents metrics; it computes from connector summaries.",
     "status": "active"},
    {"id": "g3", "title": "Sensitive data protection",
     "description": "Confidential fields are never surfaced in raw form to end users.",
     "status": "active"},
    {"id": "g4", "title": "PII masking and aggregation",
     "description": ("Customer PII (email, phone, name) is masked. The assistant prefers aggregate "
                     "insights and masks personal details when individual records are referenced."),
     "status": "active"},
    {"id": "g5", "title": "Out-of-scope refusal",
     "description": "Questions unrelated to the company or its data are politely declined.",
     "status": "active"},
    {"id": "g6", "title": "Brand-safe professional tone",
     "description": "All responses maintain a professional, brand-safe tone.",
     "status": "active"},
]

DEFAULT_ROLES = [
    {"name": "Owner",
     "description": "Full access to all connectors, governance settings, and API keys.",
     "permissions": ["read:all", "write:all", "manage:connectors", "manage:keys", "view:audit"]},
    {"name": "Analyst",
     "description": "Can query connectors and the assistant, view aggregated insights.",
     "permissions": ["read:knowledge", "read:connectors:aggregated", "use:assistant"]},
    {"name": "Support Agent",
     "description": "Can use the assistant and view ticketing trends with masked PII.",
     "permissions": ["read:knowledge", "read:ticketing:aggregated", "use:assistant"]},
    {"name": "Viewer",
     "description": "Read-only access to the website knowledge base.",
     "permissions": ["read:knowledge"]},
    # --- Business personas (used by the persona login) ---
    {"name": "Customer",
     "description": "External customer. Can chat with the public assistant and browse "
                    "the knowledge base only — no internal CRM/ERP/ticketing data.",
     "permissions": ["read:knowledge", "use:assistant"]},
    {"name": "Accountant",
     "description": "Finance staff. Aggregated connector + financial insights and the "
                    "assistant; can inspect the audit trail. Cannot provision stacks.",
     "permissions": ["read:knowledge", "use:assistant",
                     "read:connectors:aggregated", "read:ticketing:aggregated",
                     "view:audit"]},
    {"name": "CFO",
     "description": "Chief Financial Officer. Full read access across all data and the "
                    "audit trail, can provision and query, plus compliance oversight.",
     "permissions": ["read:all", "use:assistant", "view:audit",
                     "manage:connectors"]},
    {"name": "CEO",
     "description": "Chief Executive Officer. Full executive access: all data, audit, "
                    "provisioning, and governance oversight.",
     "permissions": ["read:all", "write:all", "use:assistant", "view:audit",
                     "manage:connectors"]},
]

# Roles selectable from the public persona login (never administrative roles).
LOGIN_ROLES = ["Customer", "Accountant", "CFO", "CEO"]
