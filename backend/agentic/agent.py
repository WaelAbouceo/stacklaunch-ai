"""Tool-calling agent loop — the agentic core of StackLaunch.

Instead of the single-shot RAG in /api/ask (classify -> one LLM call), this runs a
ReAct-style loop: the model is given a catalogue of governed tools (tools.py),
decides which to call, observes the JSON results, and iterates up to a step budget
before producing a grounded final answer.

Governance is accumulated *from the tools actually used*: sources, the
observability deltas, and audit-event types are derived from real tool calls
rather than guessed from a regex intent. If no LLM is configured, the loop falls
back to the deterministic assistant so the endpoint always works.
"""

from __future__ import annotations

import json
from typing import Awaitable, Callable

from data import analytics
from agentic import assistant
from governance import audit_events as governance
from core import llm
from governance import orgmodel
from governance import pii
from governance import rbac
from agentic import tools as tools_module
from agentic.tools import Tool, ToolContext

# A chat function takes (messages, tool_schemas) and returns the normalised
# {"content", "tool_calls"} dict (see llm.chat_with_tools). Injectable for tests.
ChatFn = Callable[[list[dict], list[dict]], "Awaitable[dict | None]"]

# An emit callback receives event dicts for streaming. Optional.
EmitFn = Callable[[dict], "Awaitable[None] | None"]

MAX_STEPS = 6

_SYSTEM_PROMPT = (
    "You are the governed enterprise AI assistant for {company} ({industry}). "
    "You answer business questions by calling the provided tools to retrieve real, "
    "governed data. Plan which tools you need, call them (you may call several "
    "across multiple turns), then write a concise, concrete answer grounded ONLY in "
    "the tool results.\n\n"
    "Rules:\n"
    "- Never invent numbers; cite the figures returned by tools.\n"
    "- Reference individual customers by ID and segment only — never names, emails, "
    "or phone numbers.\n"
    "- If a question is outside the company's governed data (e.g. weather, sports, "
    "general trivia), politely decline instead of calling tools.\n"
    "- Follow-up questions about your OWN previous answers (e.g. 'how did you reach "
    "this?', 'why?', 'the above') are in scope: explain your reasoning and cite which "
    "tools and figures you used. Re-call a tool if you need to verify a number.\n"
    "- Prefer the website knowledge base and connector tools; use web_search only "
    "when the answer is not available internally.\n"
    "- When you have enough information, stop calling tools and answer."
)


def _connector_in_scope(tool: Tool, ctx: ToolContext) -> bool:
    """Whether a tool's data is within the caller's department scope."""
    dept_scoped = ctx.department is not None and ctx.admin_tier not in (None, "system")
    if tool.cross_department:
        # Cross-department tools are only for org-wide (system / unscoped) callers.
        return not dept_scoped
    if not tool.connector:
        return True
    owner = ctx.project.get("connectors", {}).get(tool.connector, {}).get("department")
    return orgmodel.department_in_scope(ctx.department, ctx.admin_tier, owner)


_CONNECTOR_NAMES = {"crm": "CRM", "erp": "ERP", "ticketing": "ticketing"}


def _access_block(visible: list[Tool], project: dict) -> str:
    """A factual statement of the data sources THIS caller can actually reach, so
    the assistant never overstates its access (e.g. an external user claiming it
    can see internal connectors). Derived from the caller's visible tool set."""
    names = {t.name for t in visible}
    accessible: list[str] = []
    if names & {"search_knowledge_base", "get_company_overview"}:
        accessible.append("the company's public website knowledge base")

    in_scope = sorted({t.connector for t in visible if t.connector})
    connectors = project.get("connectors", {})
    if in_scope:
        parts = []
        for c in in_scope:
            dept = connectors.get(c, {}).get("department")
            parts.append(f"{_CONNECTOR_NAMES.get(c, c)} analytics"
                         + (f" ({dept})" if dept else ""))
        accessible.append("aggregated " + ", ".join(parts))
    if "web_search" in names:
        accessible.append("approved public web search")

    missing = [_CONNECTOR_NAMES[c] for c in ("crm", "erp", "ticketing")
               if c not in in_scope]

    lines = ["\n\nDATA ACCESS (enforced by RBAC for this session):"]
    lines.append("- You CAN access: " + ("; ".join(accessible) if accessible else "no data sources"))
    if missing:
        lines.append(
            "- You CANNOT access internal " + ", ".join(missing) + " data — it is "
            "restricted to the owning department and clearance level."
        )
    lines.append(
        "- When asked what data, systems, or databases you can access, describe ONLY "
        "the sources under 'You CAN access' above. Never claim access to anything "
        "under 'You CANNOT access', and never imply you can see internal data you "
        "have not actually retrieved from a tool."
    )
    return "\n".join(lines)


async def _emit(emit: EmitFn | None, event: dict) -> None:
    if emit is None:
        return
    res = emit(event)
    if hasattr(res, "__await__"):
        await res  # type: ignore[func-returns-value]


def _merge_obs(into: dict, delta: dict) -> None:
    for k, v in delta.items():
        into[k] = into.get(k, 0) + v


def _build_messages(ctx: ToolContext, question: str) -> list[dict]:
    system = _SYSTEM_PROMPT.format(
        company=ctx.company, industry=ctx.project.get("industryLabel", "")
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]


async def run_agent(
    project: dict,
    question: str,
    *,
    allow_search: bool = True,
    max_steps: int = MAX_STEPS,
    permissions: set[str] | None = None,
    caller_role: str | None = None,
    clearance: str = "restricted",
    admin_tier: str | None = "system",
    department: str | None = None,
    tool_names: list[str] | None = None,
    system_prompt: str | None = None,
    mode_label: str = "agent",
    history: list[dict] | None = None,
    chat_fn: ChatFn | None = None,
    emit: EmitFn | None = None,
) -> dict:
    """Run the tool-calling loop and return the assembled, governed result.

    `permissions` is the caller's RBAC permission set; when None, full access is
    assumed (direct/in-process calls and tests). Tool calls the caller isn't
    authorised for are denied and surfaced to the model as governance refusals.

    `tool_names` restricts the catalogue (used by specialist sub-agents);
    `system_prompt` overrides the default instructions; `mode_label` tags the
    result's `mode` field (e.g. a specialist's name).
    """
    # None => unrestricted (back-compat); otherwise enforce the caller's grants.
    perms = rbac.ALL_PERMISSIONS if permissions is None else permissions
    summary = analytics.build_cross_source_summary(project["connectors"])
    company = project.get("companyName", "the company")
    ctx = ToolContext(
        project=project, summary=summary, company=company, allow_search=allow_search,
        clearance=clearance, admin_tier=admin_tier, department=department,
    )

    chat = chat_fn or llm.chat_with_tools
    catalogue = tools_module.build_registry(allow_search=allow_search)
    if tool_names is not None:
        allowed = set(tool_names)
        catalogue = [t for t in catalogue if t.name in allowed]
    # Full map is kept for call-time enforcement (defense in depth), but the model
    # is only *shown* the tools this caller is permitted to use (least privilege),
    # so a low-privilege seat doesn't waste turns attempting denied tools. A tool is
    # visible only if the caller holds the permission AND the connector it reads is
    # within the caller's department scope.
    by_name = tools_module.registry_by_name(catalogue)
    visible = [
        t for t in catalogue
        if rbac.has_any(perms, t.permissions) and _connector_in_scope(t, ctx)
    ]
    schemas = [t.to_openai_schema() for t in visible]

    # No LLM (or tool-calling unavailable) -> deterministic fallback.
    if not llm.is_enabled() and chat_fn is None:
        return await _fallback(project, question, summary, reason="no_llm")

    messages = _build_messages(ctx, question)
    if system_prompt is not None:
        messages[0] = {"role": "system", "content": system_prompt}
    # Factual, scope-accurate statement of what THIS caller can reach, so the
    # assistant can't overstate its access (e.g. external user claiming connectors).
    messages[0]["content"] += _access_block(visible, project)
    if caller_role:
        # Tell the assistant who it is serving so it can answer identity/role
        # questions ("who am I?") and tailor depth. A role is not sensitive PII.
        scope_bits = [f"signed in as '{caller_role}'"]
        if department:
            scope_bits.append(f"in the {department} department")
        scope_bits.append(f"with {clearance} data clearance")
        messages[0]["content"] += (
            f"\n\nThe person you are assisting is {', '.join(scope_bits)}. If they ask "
            f"who they are, their role, department, or what they can access, tell them "
            f"plainly — this is allowed, not PII. Some tools and data are restricted to "
            f"their department and clearance; if a tool returns a 'department_scope' or "
            f"'clearance_required' error, explain that the data is outside their access "
            f"and suggest who could help, rather than guessing the numbers."
        )
    if history:
        # Insert prior conversation turns between the system prompt and the new question.
        prior = [{"role": h["role"], "content": h["content"]} for h in history
                 if h.get("role") in ("user", "assistant") and h.get("content")]
        messages = [messages[0], *prior, messages[-1]]
    sources: list[str] = []
    computed_from: list[str] = []
    audit_types: list[str] = []
    obs: dict = {"totalAssistantAnswers": 1}
    used_search = False
    tools_used: list[str] = []

    final_content: str | None = None

    for step in range(1, max_steps + 1):
        await _emit(emit, {"type": "step", "step": step})
        reply = await chat(messages, schemas)

        if reply is None:
            return await _fallback(project, question, summary, reason="llm_error")

        content = reply.get("content")
        calls = reply.get("tool_calls") or []

        if not calls:
            final_content = content
            break

        # Record the assistant turn (with its tool calls) in history.
        messages.append(
            {
                "role": "assistant",
                "content": content or "",
                "tool_calls": [
                    {
                        "id": c["id"],
                        "type": "function",
                        "function": {
                            "name": c["name"],
                            "arguments": json.dumps(c.get("arguments", {})),
                        },
                    }
                    for c in calls
                ],
            }
        )

        for call in calls:
            name = call["name"]
            args = call.get("arguments", {})
            tool: Tool | None = by_name.get(name)
            await _emit(emit, {"type": "tool_call", "name": name, "arguments": args})

            if tool is None:
                result = {"error": f"Unknown tool '{name}'."}
            elif not rbac.has_any(perms, tool.permissions):
                # Enforced RBAC: deny and surface as a governance refusal.
                result = {
                    "error": "permission_denied",
                    "message": (
                        f"Your role lacks permission to use '{name}' "
                        f"(requires one of: {tool.permissions})."
                    ),
                }
                obs["guardrailBlocks"] = obs.get("guardrailBlocks", 0) + 1
                if "guardrail_triggered" not in audit_types:
                    audit_types.append("guardrail_triggered")
            elif not _connector_in_scope(tool, ctx):
                # Enforced department scope: data belongs to another department, or
                # the tool spans departments and the caller is single-department.
                if tool.cross_department:
                    msg = (
                        f"'{name}' combines data across departments and requires "
                        f"organization-wide access. Your seat is scoped to {ctx.department}."
                    )
                else:
                    owner = ctx.project.get("connectors", {}).get(tool.connector, {}).get("department")
                    msg = (
                        f"'{name}' reads {owner} data. Your seat is scoped to "
                        f"{ctx.department or 'your department'} and cannot access it."
                    )
                result = {"error": "department_scope", "message": msg}
                obs["guardrailBlocks"] = obs.get("guardrailBlocks", 0) + 1
                if "guardrail_triggered" not in audit_types:
                    audit_types.append("guardrail_triggered")
            else:
                try:
                    result = await tool.run(ctx, args)
                except Exception as exc:  # keep the loop resilient
                    result = {"error": f"Tool '{name}' failed: {exc}"}
                else:
                    _accumulate(tool, sources, computed_from, audit_types, obs)
                    tools_used.append(name)
                    if name == "web_search" and result.get("results"):
                        used_search = True

            # Prompt-injection signal from untrusted-text tools (private field).
            if isinstance(result, dict) and result.pop("_injection", 0):
                obs["promptInjectionsNeutralized"] = obs.get("promptInjectionsNeutralized", 0) + 1
                if "guardrail_triggered" not in audit_types:
                    audit_types.append("guardrail_triggered")

            # Enforced input guardrail: scrub PII from tool output before it ever
            # reaches the model (external web/page text is the main risk surface).
            redacted = pii.redact_obj(result)
            result = redacted.text
            if redacted.count:
                _record_pii(redacted.count, sources, audit_types, obs)

            await _emit(
                emit, {"type": "tool_result", "name": name, "result": result}
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(result, default=str)[:6000],
                }
            )
    else:
        # Loop exhausted without a final answer — ask once more for a summary.
        messages.append(
            {
                "role": "user",
                "content": "Provide your final answer now using the data you gathered.",
            }
        )
        reply = await chat(messages, schemas)
        final_content = (reply or {}).get("content") if reply else None

    if not final_content:
        # The model never produced prose (or declined). Fall back deterministically.
        return await _fallback(project, question, summary, reason="empty_answer")

    # Enforced output guardrail: scrub any PII the model may have echoed back.
    scrubbed = pii.redact_text(final_content)
    final_content = scrubbed.text
    guardrail_note = None
    if scrubbed.count:
        _record_pii(scrubbed.count, sources, audit_types, obs)
        guardrail_note = (
            "PII masking applied to the response: "
            f"{scrubbed.count} sensitive value(s) redacted."
        )

    audit_types = ["assistant_answered", *_dedupe(audit_types)]
    audit_events = governance.build_audit_events(audit_types, question)
    result = {
        "content": final_content,
        "sources": _dedupe(sources),
        "computedFrom": _dedupe(computed_from),
        "guardrailNote": guardrail_note,
        "observabilityDelta": obs,
        "auditEvents": audit_events,
        "usedSearch": used_search,
        "toolsUsed": tools_used,
        "llm": llm.provider_info(),
        "mode": mode_label,
    }
    await _emit(emit, {"type": "final", **result})
    return result


def _record_pii(count: int, sources: list[str], audit_types: list[str], obs: dict) -> None:
    obs["piiMaskingEvents"] = obs.get("piiMaskingEvents", 0) + count
    if "pii_masking_applied" not in audit_types:
        audit_types.append("pii_masking_applied")


def _accumulate(
    tool: Tool,
    sources: list[str],
    computed_from: list[str],
    audit_types: list[str],
    obs: dict,
) -> None:
    sources.extend(tool.sources)
    computed_from.append(tool.name)
    audit_types.extend(tool.audit_types)
    _merge_obs(obs, tool.observability)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


async def _fallback(
    project: dict, question: str, summary: dict, *, reason: str
) -> dict:
    """Deterministic single-shot answer when the agent loop can't run."""
    result = assistant.answer_question(project, question, summary)
    audit_events = governance.build_audit_events(result["auditTypes"], question)
    return {
        "content": result["content"],
        "sources": result["sources"],
        "computedFrom": result["computedFrom"],
        "guardrailNote": result.get("guardrailNote"),
        "observabilityDelta": result["observabilityDelta"],
        "auditEvents": audit_events,
        "usedSearch": False,
        "toolsUsed": [],
        "llm": llm.provider_info(),
        "mode": f"fallback:{reason}",
    }
