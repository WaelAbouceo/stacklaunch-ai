"""Multi-agent orchestration — a supervisor over specialist sub-agents.

The single agent (`agent.run_agent`) is great for direct questions, but a
best-in-class regulated stack separates concerns into specialists with least
privilege. This module implements the well-known *agent-as-tool* pattern:

    Supervisor (router/synthesizer)
      ├─ Knowledge Specialist   — website KB + approved web search only
      └─ Data Specialist        — governed CRM/ERP/ticketing analytics only

The supervisor sees two delegate "tools" — `ask_knowledge_specialist` and
`ask_data_specialist` — and decides which (or both) to consult, then synthesises a
final answer. Each specialist is a restricted `run_agent` with its own tool subset,
focused prompt, and the SAME RBAC permission set (so a specialist can never exceed
the caller's grants). A deterministic compliance pass then scrubs the synthesised
answer for PII (defence in depth on top of each specialist's own scrubbing).
"""

from __future__ import annotations

import json

from agentic import agent as agent_module
from data import analytics
from governance import audit_events as governance
from core import llm
from governance import pii
from governance import rbac
from agentic.agent import ChatFn, EmitFn, _emit, _dedupe, _merge_obs

KNOWLEDGE_TOOLS = ["get_company_overview", "search_knowledge_base", "web_search"]
DATA_TOOLS = [
    "get_crm_summary", "get_erp_summary", "get_ticketing_summary",
    "get_cross_source_insights", "list_at_risk_customers",
]

_KNOWLEDGE_PROMPT = (
    "You are the Knowledge Specialist for {company}. Answer ONLY about the company's "
    "website/public information using your tools (website knowledge base and approved "
    "web search). Be factual and cite page titles/URLs. If you can't find it, say so."
)
_DATA_PROMPT = (
    "You are the Data Specialist for {company}. Answer using ONLY the governed "
    "connector analytics tools (CRM, ERP, ticketing, cross-source). Never expose PII; "
    "reference customers by ID and segment only. Cite the figures the tools return."
)
_SUPERVISOR_PROMPT = (
    "You are the Supervisor agent for {company}, a governed enterprise AI stack. You "
    "coordinate two specialists by calling them as tools:\n"
    "- ask_knowledge_specialist: questions about the company's website / public info.\n"
    "- ask_data_specialist: questions about internal CRM, ERP, or support-ticket data.\n\n"
    "Decide which specialist(s) to consult (you may use both for cross-cutting "
    "questions), pass them a focused sub-question, then synthesise ONE concise, "
    "grounded answer. Do not invent data; rely on specialist results. Decline "
    "out-of-scope questions (weather, sports, trivia) without calling specialists."
)


def _supervisor_schemas() -> list[dict]:
    delegate_params = {
        "type": "object",
        "properties": {
            "sub_question": {"type": "string",
                             "description": "A focused question for the specialist."}
        },
        "required": ["sub_question"],
        "additionalProperties": False,
    }
    return [
        {"type": "function", "function": {
            "name": "ask_knowledge_specialist",
            "description": "Delegate a website/public-info question to the Knowledge Specialist.",
            "parameters": delegate_params}},
        {"type": "function", "function": {
            "name": "ask_data_specialist",
            "description": "Delegate an internal-data (CRM/ERP/ticketing) question to the Data Specialist.",
            "parameters": delegate_params}},
    ]


async def run_orchestrator(
    project: dict,
    question: str,
    *,
    allow_search: bool = True,
    permissions: set[str] | None = None,
    caller_role: str | None = None,
    clearance: str = "restricted",
    admin_tier: str | None = "system",
    department: str | None = None,
    max_steps: int = 4,
    history: list[dict] | None = None,
    chat_fn: ChatFn | None = None,
    emit: EmitFn | None = None,
) -> dict:
    """Supervisor loop that delegates to specialist sub-agents and synthesises."""
    perms = rbac.ALL_PERMISSIONS if permissions is None else permissions
    company = project.get("companyName", "the company")
    chat = chat_fn or llm.chat_with_tools

    if not llm.is_enabled() and chat_fn is None:
        # No LLM: fall back to the single deterministic agent.
        return await agent_module.run_agent(
            project, question, allow_search=allow_search, permissions=permissions,
            chat_fn=chat_fn, emit=emit, mode_label="fallback:no_llm",
        )

    async def run_specialist(name: str, tool_names: list[str], prompt: str,
                             sub_q: str) -> dict:
        await _emit(emit, {"type": "delegate", "specialist": name, "question": sub_q})
        res = await agent_module.run_agent(
            project, sub_q, allow_search=allow_search, permissions=permissions,
            caller_role=caller_role, clearance=clearance, admin_tier=admin_tier,
            department=department, tool_names=tool_names,
            system_prompt=prompt.format(company=company),
            mode_label=name, chat_fn=chat_fn, emit=emit, max_steps=max_steps,
        )
        await _emit(emit, {"type": "delegate_result", "specialist": name,
                           "content": res["content"]})
        return res

    schemas = _supervisor_schemas()
    supervisor_system = _SUPERVISOR_PROMPT.format(company=company)
    if caller_role:
        supervisor_system += (
            f"\n\nThe person you are assisting is signed in with the role "
            f"'{caller_role}'. If they ask who they are or what they can access, answer "
            f"with their role plainly (this is allowed, not PII) and tailor detail to it."
        )
    messages = [
        {"role": "system", "content": supervisor_system},
    ]
    if history:
        # Prior conversation turns so follow-ups resolve against real context.
        messages += [
            {"role": h["role"], "content": h["content"]}
            for h in history
            if h.get("role") in ("user", "assistant") and h.get("content")
        ]
    messages.append({"role": "user", "content": question})

    sources: list[str] = []
    computed_from: list[str] = []
    audit_types: list[str] = ["assistant_answered"]
    obs: dict = {"totalAssistantAnswers": 1}
    specialists_used: list[str] = []
    final_content: str | None = None

    for step in range(1, max_steps + 1):
        await _emit(emit, {"type": "supervisor_step", "step": step})
        reply = await chat(messages, schemas)
        if reply is None:
            return await agent_module.run_agent(
                project, question, allow_search=allow_search, permissions=permissions,
                chat_fn=chat_fn, emit=emit, mode_label="fallback:llm_error")

        calls = reply.get("tool_calls") or []
        if not calls:
            final_content = reply.get("content")
            break

        messages.append({
            "role": "assistant", "content": reply.get("content") or "",
            "tool_calls": [{"id": c["id"], "type": "function",
                            "function": {"name": c["name"],
                                         "arguments": json.dumps(c.get("arguments", {}))}}
                           for c in calls],
        })

        for call in calls:
            name = call["name"]
            sub_q = (call.get("arguments") or {}).get("sub_question", question)
            if name == "ask_knowledge_specialist":
                res = await run_specialist("knowledge_specialist", KNOWLEDGE_TOOLS,
                                           _KNOWLEDGE_PROMPT, sub_q)
            elif name == "ask_data_specialist":
                res = await run_specialist("data_specialist", DATA_TOOLS,
                                           _DATA_PROMPT, sub_q)
            else:
                res = {"content": f"Unknown specialist '{name}'.", "sources": [],
                       "computedFrom": [], "observabilityDelta": {}, "auditEvents": []}

            specialists_used.append(name)
            sources.extend(res.get("sources", []))
            computed_from.extend(res.get("computedFrom", []))
            _merge_obs(obs, {k: v for k, v in res.get("observabilityDelta", {}).items()
                             if k != "totalAssistantAnswers"})
            messages.append({"role": "tool", "tool_call_id": call["id"],
                             "content": json.dumps({"answer": res.get("content", "")})[:6000]})

    if not final_content:
        # Ask the supervisor to synthesise from gathered specialist answers.
        messages.append({"role": "user",
                         "content": "Now synthesise the specialists' findings into one final answer."})
        reply = await chat(messages, schemas)
        final_content = (reply or {}).get("content") if reply else None

    if not final_content:
        return await agent_module.run_agent(
            project, question, allow_search=allow_search, permissions=permissions,
            chat_fn=chat_fn, emit=emit, mode_label="fallback:empty_answer")

    # Compliance pass: deterministic PII scrub of the synthesised answer.
    scrubbed = pii.redact_text(final_content)
    final_content = scrubbed.text
    guardrail_note = None
    if scrubbed.count:
        obs["piiMaskingEvents"] = obs.get("piiMaskingEvents", 0) + scrubbed.count
        if "pii_masking_applied" not in audit_types:
            audit_types.append("pii_masking_applied")
        guardrail_note = f"Compliance pass redacted {scrubbed.count} PII value(s)."

    audit_events = governance.build_audit_events(_dedupe(audit_types), question)
    result = {
        "content": final_content,
        "sources": _dedupe(sources),
        "computedFrom": _dedupe(computed_from),
        "guardrailNote": guardrail_note,
        "observabilityDelta": obs,
        "auditEvents": audit_events,
        "specialistsUsed": specialists_used,
        "llm": llm.provider_info(),
        "mode": "orchestrator",
    }
    await _emit(emit, {"type": "final", **result})
    return result
