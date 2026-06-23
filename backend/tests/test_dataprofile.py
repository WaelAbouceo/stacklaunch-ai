"""Tests for LLM-grounded dataset generation (data profile).

The LLM call itself is exercised only via normalisation (llm._normalise_profile);
generation is checked with a hand-built profile so it stays offline + deterministic.
"""

from data import datagen
from core import llm
from data import projectbuilder

PROFILE = {
    "currency": "EGP",
    "segments": ["Red Postpaid", "Flex Prepaid", "Vodafone Cash", "Enterprise"],
    "cities": ["Cairo", "Giza", "Alexandria"],
    "products": [
        {"entity_type": "plan", "name": "Red 200"},
        {"entity_type": "plan", "name": "Flex 50"},
        {"entity_type": "service", "name": "Vodafone Cash"},
        {"entity_type": "product", "name": "eSIM"},
    ],
    "ticket_categories": ["Network Issue", "Billing Dispute", "Vodafone Cash", "SIM Swap"],
    "scale": {"ltv": [2000, 120000], "monthly_revenue": [500000, 9000000]},
}


def test_crm_uses_profile_segments_and_cities():
    crm = datagen.generate_crm("telecom", "seed", 60, PROFILE)
    segments = {r["segment"] for r in crm}
    cities = {r["city"] for r in crm}
    assert segments <= set(PROFILE["segments"])
    assert cities <= set(PROFILE["cities"])
    # Scale range respected.
    assert all(2000 <= r["lifetimeValueEgp"] <= 120000 for r in crm)


def test_erp_uses_real_offerings():
    erp = datagen.generate_erp("telecom", "seed", 40, PROFILE)
    base_names = {n["name"] for n in PROFILE["products"]}
    # Every ERP record's name is a real offering (possibly with a "(n)" variant suffix).
    for r in erp:
        root = r["name"].split(" (")[0]
        assert root in base_names
    assert all(500000 <= r["revenueEgp"] <= 9000000 for r in erp)


def test_ticketing_links_to_real_products_and_categories():
    crm = datagen.generate_crm("telecom", "seed", 60, PROFILE)
    erp = datagen.generate_erp("telecom", "seed", 40, PROFILE)
    tickets = datagen.generate_ticketing("telecom", "seed", crm, erp, 80, PROFILE)
    cats = {t["category"] for t in tickets}
    assert cats <= set(PROFILE["ticket_categories"])
    linked = {t["linkedEntity"] for t in tickets if t["linkedEntity"]}
    erp_names = {r["name"] for r in erp}
    assert linked and linked <= erp_names


def test_generation_is_deterministic_with_profile():
    a = datagen.generate_erp("telecom", "seed", 40, PROFILE)
    b = datagen.generate_erp("telecom", "seed", 40, PROFILE)
    assert a == b


def test_falls_back_to_industry_templates_without_profile():
    from data.industries import INDUSTRIES
    crm = datagen.generate_crm("telecom", "seed", 40, None)
    assert {r["segment"] for r in crm} <= set(INDUSTRIES["telecom"]["crm_segments"])


def test_build_project_marks_grounded_and_attaches_profile():
    scan = {
        "websiteUrl": "https://www.vodafone.com.eg",
        "siteSummary": "Vodafone Egypt telecom operator.",
        "knowledgeBase": {"pagesIndexed": 3, "pages": []},
    }
    project = projectbuilder.build_project(scan, "Vodafone Egypt", "telecom", 1.0, PROFILE)
    assert project["dataProfile"] == PROFILE
    kinds = {e["type"] for e in project["audit"]}
    assert "data_profile_extracted" in kinds


def test_normalise_profile_filters_bad_input():
    raw = {
        "segments": ["A", "A", "", "x" * 50, "B"],  # dedupe, drop empty/too-long
        "cities": ["Cairo"],
        "products": [
            {"entity_type": "bogus", "name": "Thing"},  # bad type -> "product"
            {"name": ""},                                 # dropped
            "not-a-dict",                                 # dropped
        ],
        "ticket_categories": ["Billing"],
        "currency": "usd",
        "scale": {"ltv": [100, 50], "monthly_revenue": [1000, 5000]},  # ltv invalid
    }
    norm = llm._normalise_profile(raw)
    assert norm["segments"] == ["A", "B"]
    assert norm["currency"] == "USD"
    assert norm["products"] == [{"entity_type": "product", "name": "Thing"}]
    assert "ltv" not in norm["scale"]
    assert norm["scale"]["monthly_revenue"] == [1000, 5000]


def test_normalise_profile_returns_none_when_empty():
    assert llm._normalise_profile({"segments": [], "products": []}) is None
