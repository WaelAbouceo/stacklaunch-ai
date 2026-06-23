"""Regulatory control mappings.

Maps the platform's enforced controls to the obligations of common regimes
(GDPR, HIPAA, PCI-DSS, SOC 2, AML/KYC, EU AI Act). This is what lets a regulated
buyer see *which* technical control satisfies *which* requirement — a core part of
"best-in-class for regulated industries." Each control references the module that
implements it, so the mapping reflects real enforcement, not aspiration.
"""

from __future__ import annotations

CONTROLS = [
    {
        "id": "pii-redaction",
        "title": "Deterministic PII/PHI redaction",
        "implementedBy": "governance/pii.py (enforced in agentic agent + orchestrator)",
        "status": "enforced",
        "regulations": {
            "GDPR": ["Art.5(1)(c) data minimisation", "Art.32 security of processing"],
            "HIPAA": ["§164.514 de-identification of PHI"],
            "PCI-DSS": ["Req.3 protect stored cardholder data"],
        },
    },
    {
        "id": "tamper-evident-audit",
        "title": "Hash-chained, HMAC-signed audit trail",
        "implementedBy": "governance/auditstore.py",
        "status": "enforced",
        "regulations": {
            "SOC2": ["CC7.2 monitoring", "CC7.3 evaluation of events"],
            "GDPR": ["Art.30 records of processing", "Art.5(2) accountability"],
            "AML/KYC": ["Auditability of decisions and data access"],
        },
    },
    {
        "id": "rbac",
        "title": "Role-based access control (least privilege)",
        "implementedBy": "governance/rbac.py + governance/security.py (enforced on tools + endpoints)",
        "status": "enforced",
        "regulations": {
            "SOC2": ["CC6.1 logical access controls", "CC6.3 least privilege"],
            "HIPAA": ["§164.312(a) access control"],
            "GDPR": ["Art.32 access restriction"],
        },
    },
    {
        "id": "authn",
        "title": "API-key authentication + rate limiting",
        "implementedBy": "governance/security.py",
        "status": "enforced",
        "regulations": {
            "SOC2": ["CC6.1 authentication", "CC6.6 boundary protection"],
            "PCI-DSS": ["Req.8 identify and authenticate access"],
        },
    },
    {
        "id": "prompt-injection",
        "title": "Prompt-injection quarantine of untrusted content",
        "implementedBy": "governance/guardrails.py (web + crawled text)",
        "status": "enforced",
        "regulations": {
            "EU-AI-Act": ["Art.15 accuracy, robustness and cybersecurity"],
            "SOC2": ["CC7.1 detection of malicious input"],
        },
    },
    {
        "id": "grounded-answers",
        "title": "Source-grounded answers with citations",
        "implementedBy": "agentic/retrieval.py (BM25 + citation offsets), agentic/tools.py",
        "status": "enforced",
        "regulations": {
            "EU-AI-Act": ["Art.13 transparency", "Art.15 accuracy"],
        },
    },
    {
        "id": "governed-data-access",
        "title": "Governed structured data access (no free-form SQL)",
        "implementedBy": "data/database.py (schema-validated, read-only, parameterised queries)",
        "status": "enforced",
        "regulations": {
            "SOC2": ["CC6.1 logical access", "CC8.1 change/safe operations"],
            "PCI-DSS": ["Req.6.5 injection defenses"],
            "GDPR": ["Art.5(1)(c) data minimisation", "Art.32 security of processing"],
        },
    },
    {
        "id": "data-erasure",
        "title": "Right-to-erasure / data retention",
        "implementedBy": "data/appstore.delete_project",
        "status": "enforced",
        "regulations": {
            "GDPR": ["Art.17 right to erasure", "Art.5(1)(e) storage limitation"],
        },
    },
    {
        "id": "telemetry",
        "title": "Usage, cost, and latency telemetry",
        "implementedBy": "core/telemetry.py",
        "status": "enforced",
        "regulations": {
            "SOC2": ["CC7.2 system monitoring"],
        },
    },
]


def report() -> dict:
    regimes: dict[str, list[str]] = {}
    for c in CONTROLS:
        for reg in c["regulations"]:
            regimes.setdefault(reg, []).append(c["id"])
    return {
        "controls": CONTROLS,
        "coverageByRegulation": regimes,
        "enforcedCount": sum(1 for c in CONTROLS if c["status"] == "enforced"),
        "totalControls": len(CONTROLS),
    }
