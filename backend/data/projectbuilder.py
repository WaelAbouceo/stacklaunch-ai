"""Assemble a governed Project from a scan result + the user's confirmation.

Ported from the former frontend services/projectService.ts buildProject(). All
connector generation and governance wiring now happens server-side.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from data import datagen
from governance import audit_events as governance
from governance import orgmodel
from data.industries import label_for

MASK = 0xFFFFFFFF


def generate_api_key(seed: str) -> str:
    chars = "abcdef0123456789"
    h = 0
    for ch in seed:
        h = (h * 31 + ord(ch)) & MASK
    out = []
    for _ in range(32):
        h = (h * 1103515245 + 12345) & MASK
        out.append(chars[h % len(chars)])
    return "sk-stacklaunch-" + "".join(out)


def build_project(
    scan: dict,
    company_name: str,
    industry: str,
    confidence: float = 1.0,
    profile: "dict | None" = None,
) -> dict:
    """scan is the payload produced by /api/scan (knowledge base + summary).

    ``profile`` is an optional LLM-extracted data profile (real products, segments,
    cities, scale) used to ground the synthetic datasets in the actual company.
    """
    website_url = scan["websiteUrl"]
    seed = website_url
    label = label_for(industry)

    org_structure = orgmodel.build_org_structure(industry, profile)

    crm = datagen.generate_crm(industry, seed, 250, profile)
    erp = datagen.generate_erp(industry, seed, 80, profile)
    ticketing = datagen.generate_ticketing(industry, seed, crm, erp, 120, profile)

    kb = scan.get("knowledgeBase", {"pagesIndexed": 0, "pages": []})
    pages_indexed = kb.get("pagesIndexed", 0)

    grounded = bool(profile and (profile.get("products") or profile.get("segments")))
    crm_note = (
        "Generated 250 CRM customer records grounded in the site's real segments"
        if grounded else "Generated 250 CRM customer records"
    )
    erp_note = (
        f"Generated 80 ERP records grounded in {len(profile.get('products', []))} real offerings"
        if grounded else "Generated 80 ERP operational records"
    )

    audit = [
        governance.create_audit_event("website_scanned", f"Scanned {website_url} ({pages_indexed} pages)"),
        governance.create_audit_event("knowledge_base_built", f"Knowledge base built: {pages_indexed} pages indexed"),
        governance.create_audit_event("industry_detected", f"Industry detected: {label} (confidence {round(confidence * 100)}%)"),
        governance.create_audit_event(
            "org_structure_derived",
            f"Derived org structure: {len(org_structure['departments'])} departments "
            f"with {len(orgmodel.CLEARANCE_LEVELS)}-level data classification",
        ),
    ]
    if grounded:
        audit.append(governance.create_audit_event(
            "data_profile_extracted",
            f"LLM grounded datasets in {company_name}'s real offerings, segments and scale",
        ))
    audit += [
        governance.create_audit_event("mock_crm_generated", crm_note),
        governance.create_audit_event("mock_erp_generated", erp_note),
        governance.create_audit_event("mock_ticketing_generated", "Generated 120 support tickets"),
        governance.create_audit_event("pii_masking_applied", "PII masking enabled on CRM connector"),
    ]

    observability = {**governance.initial_observability(), "websiteScans": 1}
    now = "Just now"

    return {
        "id": f"proj-{int(time.time() * 1000)}",
        "websiteUrl": website_url,
        "companyName": company_name,
        "siteSummary": scan.get("siteSummary", ""),
        "industry": industry,
        "industryLabel": label,
        "industryConfidence": confidence,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "apiKey": generate_api_key(seed),
        "knowledgeBase": kb,
        "connectors": {
            "crm": {
                "id": "crm", "name": "CRM Connector", "datasetType": "Customer Records",
                "status": "Demo Connected", "recordCount": len(crm), "lastSync": now,
                "access": "Governed", "piiMasking": True, "records": crm,
                "department": orgmodel.connector_domain(org_structure, "crm")["department"],
                "classification": orgmodel.connector_domain(org_structure, "crm")["classification"],
            },
            "erp": {
                "id": "erp", "name": "ERP Connector", "datasetType": "Operations & Finance",
                "status": "Demo Connected", "recordCount": len(erp), "lastSync": now,
                "access": "Governed", "piiMasking": False, "records": erp,
                "department": orgmodel.connector_domain(org_structure, "erp")["department"],
                "classification": orgmodel.connector_domain(org_structure, "erp")["classification"],
            },
            "ticketing": {
                "id": "ticketing", "name": "Ticketing Connector", "datasetType": "Support Tickets",
                "status": "Demo Connected", "recordCount": len(ticketing), "lastSync": now,
                "access": "Governed", "piiMasking": False, "records": ticketing,
                "department": orgmodel.connector_domain(org_structure, "ticketing")["department"],
                "classification": orgmodel.connector_domain(org_structure, "ticketing")["classification"],
            },
        },
        "audit": audit,
        "observability": observability,
        "guardrails": governance.DEFAULT_GUARDRAILS,
        "roles": governance.DEFAULT_ROLES,
        "orgStructure": org_structure,
        "suggestedQuestions": _suggested_questions(industry),
        "dataProfile": profile if grounded else None,
        "analytics": None,  # filled in by the API layer after assembly
    }


def _suggested_questions(industry: str) -> list[str]:
    from data.industries import INDUSTRIES
    return INDUSTRIES.get(industry, INDUSTRIES["generic_services"])["suggested_questions"]
