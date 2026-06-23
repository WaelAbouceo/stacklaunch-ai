"""Tests for the LLM-as-judge validator, judged evals, and conversation validation.

The LLM is mocked (scripted JSON replies) so these stay deterministic and
CI-friendly while still exercising the parsing, thresholds, PII gate, and the
graceful-degradation path when no LLM is configured.
"""

import asyncio
import json

import pytest

from data import appstore
from evaluation import convvalidate
from evaluation import evals
from evaluation import judge
from core import llm
from data import projectbuilder


def _run(coro):
    return asyncio.run(coro)


def _project() -> dict:
    scan = {"websiteUrl": "https://b.com", "siteSummary": "Bank",
            "knowledgeBase": {"pagesIndexed": 1, "pages": [
                {"title": "Home", "url": "https://b.com", "summary": "Bank",
                 "topics": [], "content": "bank"}]}}
    return projectbuilder.build_project(scan, "B Bank", "banking", 1.0)


@pytest.fixture()
def llm_on(monkeypatch):
    """Force the judge's LLM path on with a scripted reply queue."""
    replies: list[str] = []
    monkeypatch.setattr(llm, "is_enabled", lambda: True)

    async def fake_chat(messages, *, json_mode=False, max_tokens=700):
        return replies.pop(0) if replies else None

    monkeypatch.setattr(llm, "_chat", fake_chat)
    return replies


# --------------------------- grade_answer ---------------------------

def test_judge_disabled_without_llm(monkeypatch):
    monkeypatch.setattr(llm, "is_enabled", lambda: False)
    grade = _run(judge.grade_answer("q?", "an answer", "context"))
    assert grade["available"] is False
    assert grade["piiLeak"] is False


def test_judge_pass_verdict(llm_on):
    llm_on.append(json.dumps({
        "groundedness": 0.95, "relevance": 0.9, "safetyPass": True,
        "refusalCorrect": True, "unsupportedClaims": [], "rationale": "Solid."}))
    grade = _run(judge.grade_answer("q?", "grounded answer", "ctx",
                                    expected_refusal=False))
    assert grade["available"] is True
    assert grade["verdict"] == "pass"
    assert grade["groundedness"] == 0.95


def test_judge_fail_on_low_groundedness(llm_on):
    llm_on.append(json.dumps({
        "groundedness": 0.2, "relevance": 0.9, "safetyPass": True,
        "refusalCorrect": True, "unsupportedClaims": ["made-up metric"],
        "rationale": "Hallucinated."}))
    grade = _run(judge.grade_answer("q?", "answer", "ctx"))
    assert grade["verdict"] == "fail"
    assert "made-up metric" in grade["unsupportedClaims"]


def test_deterministic_pii_gate_overrides_judge(llm_on):
    # Judge claims safe, but the answer leaks an email -> safety must fail.
    llm_on.append(json.dumps({
        "groundedness": 0.95, "relevance": 0.95, "safetyPass": True,
        "refusalCorrect": True, "unsupportedClaims": [], "rationale": "ok"}))
    grade = _run(judge.grade_answer(
        "q?", "Contact john.doe@example.com for details", "ctx"))
    assert grade["piiLeak"] is True
    assert grade["safetyPass"] is False
    assert grade["verdict"] == "fail"


def test_judge_passes_correct_refusal_in_live_validation(llm_on):
    # "who am i" — low relevance is expected for a refusal; a correct refusal passes.
    llm_on.append(json.dumps({
        "groundedness": 1.0, "relevance": 0.5, "safetyPass": True,
        "answerRefused": True, "refusalCorrect": True,
        "unsupportedClaims": [], "rationale": "Correctly refused to identify the user."}))
    grade = _run(judge.grade_answer("who am i", "I can't identify individuals.", "ctx"))
    assert grade["answerRefused"] is True
    assert grade["verdict"] == "pass"


def test_judge_fails_wrong_refusal_in_live_validation(llm_on):
    # Refusing an in-scope question is a failure even though it refused.
    llm_on.append(json.dumps({
        "groundedness": 1.0, "relevance": 0.2, "safetyPass": True,
        "answerRefused": True, "refusalCorrect": False,
        "unsupportedClaims": [], "rationale": "Wrongly refused an answerable question."}))
    grade = _run(judge.grade_answer("How many tickets are open?", "I cannot help.", "ctx"))
    assert grade["verdict"] == "fail"


def test_judge_unparseable_output(llm_on):
    llm_on.append("not json at all")
    grade = _run(judge.grade_answer("q?", "answer", "ctx"))
    assert grade["available"] is False
    assert grade["reason"] == "unparseable_judge_output"


def test_aggregate_rollup():
    grades = [
        {"available": True, "verdict": "pass", "groundedness": 0.9,
         "relevance": 0.8, "piiLeak": False},
        {"available": True, "verdict": "fail", "groundedness": 0.3,
         "relevance": 0.7, "piiLeak": True},
        {"available": False},
    ]
    agg = judge.aggregate(grades)
    assert agg["judged"] == 2
    assert agg["passed"] == 1
    assert agg["passRate"] == 0.5
    assert agg["piiLeaks"] == 1


# --------------------------- judged evals ---------------------------

def test_run_evals_judged_without_llm(monkeypatch):
    monkeypatch.setattr(llm, "is_enabled", lambda: False)
    report = _run(evals.run_evals_judged())
    assert report["total"] == len(evals.GOLDEN)
    assert report["judge"]["available"] is False


def test_run_evals_judged_with_llm(llm_on):
    # One reply per golden case.
    for _ in evals.GOLDEN:
        llm_on.append(json.dumps({
            "groundedness": 0.9, "relevance": 0.85, "safetyPass": True,
            "refusalCorrect": True, "unsupportedClaims": [], "rationale": "ok"}))
    report = _run(evals.run_evals_judged())
    assert report["judge"]["available"] is True
    assert report["judge"]["judged"] == len(evals.GOLDEN)
    assert all("judge" in c for c in report["cases"])


# --------------------- conversation validation ---------------------

@pytest.fixture()
def store(tmp_path):
    appstore.configure(str(tmp_path / "app.db"))
    yield appstore
    appstore.configure(appstore.config.APP_DB_PATH)


def test_validate_session_grades_assistant_turns(llm_on, store):
    project = _project()
    store.save_project(project)
    store.add_turn("sx", "user", "How many at-risk customers?", project["id"])
    store.add_turn("sx", "assistant", "There are several at-risk customers.", project["id"])

    llm_on.append(json.dumps({
        "groundedness": 0.8, "relevance": 0.8, "safetyPass": True,
        "refusalCorrect": True, "unsupportedClaims": [], "rationale": "ok"}))

    report = _run(convvalidate.validate_session("sx"))
    assert report["projectId"] == project["id"]
    assert report["turnsValidated"] == 1
    assert report["summary"]["available"] is True
    assert report["turns"][0]["judge"]["verdict"] == "pass"


def test_validate_session_no_turns(llm_on, store):
    report = _run(convvalidate.validate_session("empty"))
    assert report["turnsValidated"] == 0
    assert report["summary"]["available"] is False
