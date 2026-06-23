"""Live conversation validation with an LLM judge.

Where ``evals.py`` validates the system against a golden set *before* shipping,
this module audits what actually happened in a real session *after the fact*. It
pulls the persisted conversation turns, reconstructs the ground-truth context the
assistant was supposed to use (from the linked project's connector summaries +
website knowledge), and grades each assistant turn for groundedness, relevance,
PII safety, and policy. This is the "audit the production transcript" capability
a regulated deployment needs.
"""

from __future__ import annotations

from data import analytics
from data import appstore
from evaluation import evals
from evaluation import judge
from core import llm


def _pair_turns(turns: list[dict]) -> list[tuple[str, str]]:
    """Pair each assistant turn with the user turn that prompted it."""
    pairs: list[tuple[str, str]] = []
    last_user = ""
    for t in turns:
        role = t.get("role")
        content = t.get("content", "") or ""
        if role == "user":
            last_user = content
        elif role == "assistant":
            pairs.append((last_user, content))
    return pairs


async def validate_session(session_id: str, *, limit: int = 50) -> dict:
    """Grade every assistant turn in a stored session. Returns a structured
    report; degrades gracefully when no project context or no LLM is available."""
    turns = appstore.get_turns(session_id, limit=limit)
    pairs = _pair_turns(turns)

    project_id = appstore.get_session_project_id(session_id)
    project = appstore.get_project(project_id) if project_id else None

    report: dict = {
        "sessionId": session_id,
        "projectId": project_id,
        "turnsValidated": 0,
        "turns": [],
    }

    if not pairs:
        report["summary"] = {"available": False, "reason": "no_assistant_turns"}
        return report

    context = ""
    if project:
        summary = analytics.build_cross_source_summary(project["connectors"])
        context = evals._grading_context(project, summary)
    elif llm.is_enabled():
        # No linked project: we can still run the deterministic PII gate, but the
        # judge cannot assess groundedness without ground truth.
        report["contextWarning"] = "no_project_context"

    grades: list[dict] = []
    for question, answer in pairs:
        grade = await judge.grade_answer(question, answer, context)
        grades.append(grade)
        report["turns"].append({
            "question": question,
            "answerPreview": answer[:240],
            "judge": grade,
        })

    report["turnsValidated"] = len(pairs)
    report["summary"] = judge.aggregate(grades)
    return report
