"""A small, runnable evaluation harness.

Regulated/best-in-class stacks need measurable quality, not vibes. This harness
runs a golden set of questions against the deterministic assistant (no live LLM
needed, so it is reproducible and CI-friendly) and checks two things:

- **Groundedness**: the answer contains the expected, data-derived signal.
- **Refusal**: out-of-scope questions are declined by the guardrail.

It is intentionally lightweight; extend `GOLDEN` and the checks as the product
grows, and add an LLM-graded variant for natural-language quality.
"""

from __future__ import annotations

import json

from data import analytics
from agentic import assistant
from evaluation import judge
from core import llm
from data import projectbuilder
from agentic.assistant import answer_question, classify

GOLDEN = [
    {"q": "What are the top support ticket categories?",
     "must_include_any": ["tickets", "%"], "refusal": False},
    {"q": "Which customers are at risk of churn?",
     "must_include_any": ["at risk", "at-risk", "CUST-"], "refusal": False},
    {"q": "Which entities have high revenue but poor sentiment?",
     "must_include_any": ["revenue", "negative"], "refusal": False},
    {"q": "What's the weather tomorrow?",
     "must_include_any": ["outside the scope", "scope"], "refusal": True},
    {"q": "Give me a recipe for pizza.",
     "must_include_any": ["outside the scope", "scope"], "refusal": True},
]


def _demo_project() -> dict:
    scan = {
        "websiteUrl": "https://eval-bank.com",
        "siteSummary": "A retail bank.",
        "knowledgeBase": {"pagesIndexed": 1, "pages": [
            {"title": "Home", "url": "https://eval-bank.com", "summary": "Retail bank.",
             "topics": ["bank"], "content": "retail banking services"}]},
    }
    return projectbuilder.build_project(scan, "Eval Bank", "banking", 1.0)


def run_evals(project: dict | None = None) -> dict:
    project = project or _demo_project()
    summary = analytics.build_cross_source_summary(project["connectors"])
    cases = []
    passed = 0
    for case in GOLDEN:
        result = answer_question(project, case["q"], summary)
        content = (result["content"] or "").lower()
        is_refusal = bool(result["observabilityDelta"].get("guardrailBlocks"))
        grounded = any(tok.lower() in content for tok in case["must_include_any"])
        ok = grounded and (is_refusal == case["refusal"])
        passed += 1 if ok else 0
        cases.append({
            "question": case["q"], "passed": ok, "grounded": grounded,
            "refused": is_refusal, "expectedRefusal": case["refusal"],
            "intent": classify(case["q"]),
        })
    return {"passed": passed, "total": len(GOLDEN),
            "passRate": round(passed / len(GOLDEN), 3), "cases": cases}


def _grading_context(project: dict, summary: dict) -> str:
    """The ground-truth the judge is allowed to use.

    This must cover *everything the assistant's tools can return*, not just the
    headline summary — otherwise legitimately tool-grounded figures (per-entity
    revenue/margin/complaint-rate, full segment/city breakdowns) look
    "unsupported" and correct answers fail validation. We therefore include both a
    human-readable summary and the full connector analytics JSON, which is exactly
    what get_crm/erp/ticketing_summary and get_cross_source_insights hand back.
    """
    company = project.get("companyName", "the company")
    label = project.get("industryLabel", "")
    ctx = assistant.build_data_context(company, label, summary)

    # Full machine-readable analytics — the same data the agent's tools return.
    # Contains only aggregates and masked entity/customer fields (no raw PII).
    ctx += (
        "\n\nFULL CONNECTOR ANALYTICS (authoritative ground truth — the exact data "
        "the assistant's tools return; any figure here is supported):\n"
        + json.dumps(summary, default=str)
    )

    pages = project.get("knowledgeBase", {}).get("pages", [])[:5]
    if pages:
        kb = "\n".join(
            f"- {p.get('title', '')}: {p.get('summary', '')}" for p in pages
        )
        ctx += "\n\nWebsite knowledge:\n" + kb
    return ctx


async def run_evals_judged(project: dict | None = None) -> dict:
    """Deterministic evals + an LLM-as-judge pass per case. The deterministic
    result is always returned; the judge layer is additive and degrades to
    ``available: False`` when no LLM is configured."""
    project = project or _demo_project()
    base = run_evals(project)
    summary = analytics.build_cross_source_summary(project["connectors"])

    if not llm.is_enabled():
        base["judge"] = {"available": False, "reason": "llm_unavailable"}
        return base

    context = _grading_context(project, summary)
    grades: list[dict] = []
    for case, c in zip(GOLDEN, base["cases"]):
        result = answer_question(project, case["q"], summary)
        grade = await judge.grade_answer(
            case["q"],
            result["content"] or "",
            context,
            expected_refusal=case["refusal"],
        )
        c["judge"] = grade
        grades.append(grade)

    base["judge"] = judge.aggregate(grades)
    return base
