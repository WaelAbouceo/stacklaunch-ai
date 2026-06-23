"""StackLaunch API — the single brain of the product.

The browser only renders. This service does everything else: fetch/parse
arbitrary sites, fall back to SearXNG search when a site is unreachable, run LLM
reasoning (SovereignEG or a local Ollama fallback) for classification and the RAG
assistant, generate the internal demo datasets, compute all analytics, and apply
governance (guardrails, PII policy, audit, observability).
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # populate env before llm/search read it

from fastapi import Depends, FastAPI, Header, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from core import config  # noqa: E402
from agentic import agent  # noqa: E402
from agentic import orchestrator  # noqa: E402
from data import analytics  # noqa: E402
from data import appstore  # noqa: E402
from data import database  # noqa: E402
from agentic import assistant  # noqa: E402
from governance import auditstore  # noqa: E402
from governance import compliance  # noqa: E402
from governance import audit_events as governance  # noqa: E402
from data import industries  # noqa: E402
from core import llm  # noqa: E402
from governance import orgmodel  # noqa: E402
from data import projectbuilder  # noqa: E402
from governance import rbac  # noqa: E402
from data import search  # noqa: E402
from governance import security  # noqa: E402
from governance import sovereignty  # noqa: E402
from core import telemetry  # noqa: E402
from data.scanner import ScanError, scan_website  # noqa: E402
from governance.security import Principal  # noqa: E402

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Log the sovereign posture at boot; in strict mode `validate_startup` raises
    (and aborts startup) if the LLM endpoint is a non-allowlisted public cloud."""
    for warning in sovereignty.validate_startup():
        print(f"[sovereignty] WARNING: {warning}")
    posture = sovereignty.posture()
    res = posture["llm"]["residency"]["label"]
    print(
        f"[sovereignty] region={posture['dataRegion']} "
        f"strict={posture['strict']} llm={posture['llm']['host']} ({res})"
    )
    yield


app = FastAPI(title="StackLaunch API", version="4.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_principal(
    request: Request, x_api_key: str | None = Header(default=None)
) -> Principal:
    """Resolve + rate-limit the caller. Enforces auth only when REQUIRE_AUTH=1."""
    principal = security.resolve(x_api_key)
    if principal is None:
        if config.REQUIRE_AUTH:
            raise HTTPException(status_code=401, detail="Valid X-API-Key required.")
        principal = security.anonymous_principal()

    identity = principal.label if principal.authenticated else (
        request.client.host if request.client else "anonymous"
    )
    if not security.check_rate_limit(identity):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again shortly.")
    return principal


def require(principal: Principal, *options: str) -> None:
    if not rbac.has_any(principal.permissions, list(options)):
        raise HTTPException(
            status_code=403,
            detail=f"Role '{principal.role}' lacks permission (need one of: {list(options)}).",
        )

OVERALL_TIMEOUT = 40.0


class ScanRequest(BaseModel):
    url: str


class BuildRequest(BaseModel):
    websiteUrl: str
    companyName: str
    industry: str
    scan: dict


class AskRequest(BaseModel):
    question: str
    project: dict
    allowSearch: bool = True


class AgentRequest(BaseModel):
    question: str
    project: dict
    allowSearch: bool = True
    maxSteps: int = agent.MAX_STEPS
    sessionId: str | None = None


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "llm": llm.provider_info(),
        "searxng": await search.is_available(),
    }


@app.get("/api/sovereignty")
async def sovereignty_posture() -> dict:
    """Inspectable data-residency + egress manifest for the running stack."""
    return sovereignty.posture()


@app.get("/api/industries")
async def list_industries() -> dict:
    return {"industries": industries.industry_options()}


@app.post("/api/scan")
async def scan(req: ScanRequest, principal: Principal = Depends(get_principal)) -> dict:
    require(principal, "use:assistant", "read:knowledge")
    try:
        result = await asyncio.wait_for(scan_website(req.url), timeout=OVERALL_TIMEOUT)
    except ScanError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="The site took too long to respond. Try again or use a different URL.",
        )
    except Exception:  # pragma: no cover
        raise HTTPException(status_code=502, detail="Failed to scan the website.")

    payload = result.to_dict()

    # LLM enrichment: real company name, description, and industry classification.
    if llm.is_enabled():
        try:
            enriched = await asyncio.wait_for(
                llm.classify_site(
                    url=result.website_url,
                    company_hint=result.company_name,
                    text=result.scanned_text,
                ),
                timeout=30.0,
            )
        except (asyncio.TimeoutError, Exception):
            enriched = None
        if enriched:
            payload["companyName"] = enriched["company_name"] or payload["companyName"]
            payload["siteSummary"] = enriched["description"] or payload["siteSummary"]
            payload["industry"] = enriched["industry_key"]
            payload["industryLabel"] = enriched["industry_label"]
            payload["industryConfidence"] = enriched["confidence"]
            payload["industryTopics"] = enriched["topics"]

    # Keyword fallback when no LLM produced a classification.
    if not payload.get("industry"):
        key, conf = industries.detect_industry_by_keywords(result.scanned_text)
        payload["industry"] = key
        payload["industryLabel"] = industries.label_for(key)
        payload["industryConfidence"] = conf

    payload["llm"] = llm.provider_info()
    return payload


def _scan_text(scan: dict) -> str:
    """Best text signal from a scan payload for profile extraction."""
    text = (scan.get("scannedText") or "").strip()
    if len(text) >= 400:
        return text
    pages = (scan.get("knowledgeBase") or {}).get("pages") or []
    parts = [scan.get("siteSummary") or ""]
    for p in pages[:12]:
        parts.append(p.get("title") or "")
        parts.append(p.get("summary") or p.get("content") or "")
    return "\n".join(part for part in parts if part).strip()


async def _extract_data_profile(scan: dict, company_name: str, industry: str) -> "dict | None":
    if not llm.is_enabled():
        return None
    text = _scan_text(scan)
    if not text:
        return None
    try:
        return await asyncio.wait_for(
            llm.extract_data_profile(
                company=company_name,
                industry_label=industries.label_for(industry),
                url=scan.get("websiteUrl", ""),
                text=text,
                topics=scan.get("industryTopics"),
            ),
            timeout=30.0,
        )
    except (asyncio.TimeoutError, Exception):
        return None


@app.post("/api/build")
async def build(req: BuildRequest, principal: Principal = Depends(get_principal)) -> dict:
    """Assemble the full governed Project from the confirmed analysis."""
    require(principal, "manage:connectors", "write:all")
    industry = req.industry if req.industry in industries.VALID_KEYS else "generic_services"
    scan_payload = {**req.scan, "websiteUrl": req.websiteUrl}

    # Ground the synthetic datasets in the real site: ask the LLM for the company's
    # actual offerings/segments/scale. Best-effort — datasets fall back to generic
    # industry templates if no LLM is reachable or extraction fails.
    profile = await _extract_data_profile(scan_payload, req.companyName, industry)

    project = projectbuilder.build_project(
        scan_payload, req.companyName, industry, confidence=1.0, profile=profile
    )
    project["analytics"] = analytics.build_cross_source_summary(project["connectors"])
    # Persist the project's provisioning events into the tamper-evident audit log.
    try:
        auditstore.append_events(project.get("audit", []), project_id=project.get("id"))
    except Exception:  # auditing must never break the main flow
        pass
    try:
        appstore.save_project(project)
    except Exception:
        pass
    return project


def _build_ask_context(company: str, data_context: str, pages: list[dict], results: list) -> str:
    parts: list[str] = []
    if pages:
        parts.append("WEBSITE KNOWLEDGE (real, crawled pages):")
        for p in pages[:12]:
            body = (p.get("summary") or p.get("content") or "").strip()
            parts.append(f"- [{p.get('title','')}] ({p.get('url','')})\n  {body[:600]}")
        parts.append("")
    if data_context:
        parts.append("INTERNAL DATA SUMMARY (generated demo datasets):")
        parts.append(data_context.strip())
        parts.append("")
    if results:
        parts.append("WEB SEARCH RESULTS (SearXNG):")
        for r in results:
            parts.append(f"- [{r.title}] ({r.url})\n  {r.content[:400]}")
        parts.append("")
    return "\n".join(parts)


@app.post("/api/ask")
async def ask(req: AskRequest, principal: Principal = Depends(get_principal)) -> dict:
    """Full assistant pipeline on the backend: classify -> governance metadata ->
    grounded LLM answer (with SearXNG augmentation) -> audit + observability."""
    require(principal, "use:assistant")
    project = req.project
    if not project or "connectors" not in project:
        raise HTTPException(status_code=422, detail="A built project is required.")

    company = project.get("companyName", "the company")
    summary = analytics.build_cross_source_summary(project["connectors"])

    # Deterministic reasoning produces governance metadata + the fallback answer.
    intent = assistant.classify(req.question)
    result = assistant.answer_question(project, req.question, summary)
    is_refusal = bool(result["observabilityDelta"].get("guardrailBlocks"))

    content = result["content"]
    used_search = False

    if not is_refusal and llm.is_enabled():
        pages = project.get("knowledgeBase", {}).get("pages", [])
        pages_text = " ".join((p.get("summary") or p.get("content") or "") for p in pages)
        search_results: list = []
        # Augment with web search for website-facing questions (about/general
        # knowledge) when the crawled pages are thin OR don't actually cover the
        # question — e.g. "what are your branches" isn't on the indexed pages.
        if req.allowSearch and intent in ("knowledge", "about"):
            hits = assistant.retrieve_knowledge(pages, req.question)
            top_score = hits[0]["score"] if hits else 0
            if top_score < 3 or len(pages_text) < 800:
                query = f"{company} {req.question}"
                search_results = await search.search(query, max_results=5)
        data_context = assistant.build_data_context(
            company, project.get("industryLabel", ""), summary
        )
        context = _build_ask_context(company, data_context, pages, search_results)
        try:
            text = await asyncio.wait_for(
                llm.answer(question=req.question, company=company, context=context),
                timeout=45.0,
            )
        except (asyncio.TimeoutError, Exception):
            text = None
        if text:
            content = text
            used_search = bool(search_results)

    sources = list(result["sources"])
    if used_search and "Approved Web Source" not in sources:
        sources.append("Approved Web Source")

    audit_events = governance.build_audit_events(result["auditTypes"], req.question)
    _persist_audit(audit_events, project.get("id"))

    return {
        "content": content,
        "sources": sources,
        "computedFrom": result["computedFrom"],
        "guardrailNote": result.get("guardrailNote"),
        "observabilityDelta": result["observabilityDelta"],
        "auditEvents": audit_events,
        "usedSearch": used_search,
        "llm": llm.provider_info(),
    }


def _persist_audit(events: list[dict], project_id: str | None) -> None:
    try:
        auditstore.append_events(events, project_id=project_id)
    except Exception:  # auditing must never break the main flow
        pass


def _validate_project(project: dict) -> None:
    if not project or "connectors" not in project:
        raise HTTPException(status_code=422, detail="A built project is required.")


@app.post("/api/agent")
async def run_agent_endpoint(
    req: AgentRequest, principal: Principal = Depends(get_principal)
) -> dict:
    """Agentic answer: the model calls governed tools (CRM/ERP/ticketing/KB/search)
    in a loop, then answers. Falls back to the deterministic assistant when no LLM
    is configured. Non-streaming JSON variant."""
    require(principal, "use:assistant")
    _validate_project(req.project)
    history = appstore.get_turns(req.sessionId) if req.sessionId else None
    result = await agent.run_agent(
        req.project,
        req.question,
        allow_search=req.allowSearch,
        max_steps=max(1, min(req.maxSteps, 10)),
        permissions=principal.permissions,
        caller_role=principal.role,
        clearance=principal.clearance,
        admin_tier=principal.admin_tier,
        department=principal.department,
        history=history,
    )
    _persist_audit(result.get("auditEvents", []), req.project.get("id"))
    if req.sessionId:
        appstore.add_turn(req.sessionId, "user", req.question, req.project.get("id"))
        appstore.add_turn(req.sessionId, "assistant", result.get("content", ""), req.project.get("id"))
    return result


@app.post("/api/orchestrate")
async def orchestrate_endpoint(
    req: AgentRequest, principal: Principal = Depends(get_principal)
) -> dict:
    """Multi-agent answer: a supervisor delegates to Knowledge and Data specialists
    (each least-privilege, RBAC-bounded), then synthesises with a compliance pass."""
    require(principal, "use:assistant")
    _validate_project(req.project)
    history = appstore.get_turns(req.sessionId) if req.sessionId else None
    result = await orchestrator.run_orchestrator(
        req.project,
        req.question,
        allow_search=req.allowSearch,
        permissions=principal.permissions,
        caller_role=principal.role,
        clearance=principal.clearance,
        admin_tier=principal.admin_tier,
        department=principal.department,
        max_steps=max(1, min(req.maxSteps, 6)),
        history=history,
    )
    _persist_audit(result.get("auditEvents", []), req.project.get("id"))
    if req.sessionId:
        pid = req.project.get("id")
        appstore.add_turn(req.sessionId, "user", req.question, pid)
        appstore.add_turn(req.sessionId, "assistant", result.get("content", ""), pid)
    return result


@app.post("/api/agent/stream")
async def run_agent_stream(
    req: AgentRequest, principal: Principal = Depends(get_principal)
) -> StreamingResponse:
    """Server-Sent Events stream of the agent's steps, tool calls, tool results,
    and final answer. Each event is a JSON object on a `data:` line."""
    require(principal, "use:assistant")
    _validate_project(req.project)

    queue: asyncio.Queue[dict | None] = asyncio.Queue()
    # Load prior conversation turns BEFORE the new question so follow-ups like
    # "how did you reach this?" / "the above" resolve against real context.
    history = appstore.get_turns(req.sessionId) if req.sessionId else None

    async def emit(event: dict) -> None:
        await queue.put(event)

    async def drive() -> None:
        try:
            result = await agent.run_agent(
                req.project,
                req.question,
                allow_search=req.allowSearch,
                max_steps=max(1, min(req.maxSteps, 10)),
                permissions=principal.permissions,
                caller_role=principal.role,
                clearance=principal.clearance,
                admin_tier=principal.admin_tier,
                department=principal.department,
                history=history,
                emit=emit,
            )
            _persist_audit(result.get("auditEvents", []), req.project.get("id"))
            # Persist this exchange so the next turn has memory.
            if req.sessionId:
                pid = req.project.get("id")
                appstore.add_turn(req.sessionId, "user", req.question, pid)
                appstore.add_turn(req.sessionId, "assistant", result.get("content", ""), pid)
        except Exception as exc:  # surface errors as a stream event
            await queue.put({"type": "error", "message": str(exc)})
        finally:
            await queue.put(None)

    async def event_source():
        task = asyncio.create_task(drive())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield f"data: {json.dumps(event, default=str)}\n\n"
        finally:
            task.cancel()

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/audit")
async def get_audit(
    limit: int = 100, projectId: str | None = None,
    principal: Principal = Depends(get_principal),
) -> dict:
    """Read the persisted, hash-chained audit trail (newest first)."""
    require(principal, "view:audit")
    limit = max(1, min(limit, 500))
    return {"events": auditstore.list_events(limit=limit, project_id=projectId)}


@app.get("/api/audit/verify")
async def verify_audit(principal: Principal = Depends(get_principal)) -> dict:
    """Recompute the hash chain to confirm the audit log hasn't been tampered with."""
    require(principal, "view:audit")
    return auditstore.verify_chain()


class CreateKeyRequest(BaseModel):
    label: str
    role: str


@app.get("/api/roles")
async def list_roles() -> dict:
    """Public: the available roles and their permission sets (for key creation UIs)."""
    return {"roles": governance.DEFAULT_ROLES}


class LoginRequest(BaseModel):
    """Seat-based sign-in: an org seat = admin tier + (optional) department/group.

    The backend derives the concrete permission set, clearance, and scope from the
    tier via orgmodel.derive_access — the client never asserts its own permissions.
    """
    tier: str
    department: str | None = None
    group: str | None = None
    workspaceId: str | None = None


_TIER_DESCRIPTIONS = {
    "system": "Platform-wide administrator. Full access across all departments, "
              "data, audit, and provisioning.",
    "department": "Department head. Full access to their department's data and "
                  "audit up to Restricted; can provision and manage department keys.",
    "group": "Group lead. Aggregated access to their department's data up to "
             "Confidential; can mint keys for their group.",
    "member": "Department staff. Aggregated insights and the assistant, scoped to "
              "their department up to Internal.",
    "external": "External user. Public assistant and knowledge base only.",
}


def _org_for_workspace(workspace_id: str | None) -> dict | None:
    if not workspace_id:
        return None
    proj = appstore.get_project(workspace_id)
    return proj.get("orgStructure") if proj else None


@app.get("/api/login/seats")
async def login_seats(workspaceId: str | None = None) -> dict:
    """Public: the org chart + selectable seats for a workspace (or a generic
    default before any workspace is chosen, e.g. when provisioning a new stack)."""
    org = _org_for_workspace(workspaceId) or orgmodel.build_org_structure("generic_services")
    return {"org": org, "seats": orgmodel.seats_catalog(org)}


@app.post("/api/login")
async def login(req: LoginRequest, request: Request) -> dict:
    """Seat sign-in. Mints a scoped, revocable API key carrying the seat's expanded
    permissions, clearance, and org scope. The plaintext key is returned once and
    sent as X-API-Key on subsequent calls, so RBAC is enforced per seat."""
    if req.tier not in orgmodel.ADMIN_TIERS:
        raise HTTPException(
            status_code=403,
            detail=f"Unknown seat tier '{req.tier}'. Valid: {orgmodel.ADMIN_TIERS}.",
        )

    department, group = req.department, req.group
    # Validate scope against the workspace's real org chart when provided.
    if req.tier not in ("system", "external"):
        org = _org_for_workspace(req.workspaceId)
        if org:
            depts = {d["name"]: d for d in org["departments"]}
            if department and department not in depts:
                raise HTTPException(status_code=400, detail=f"Unknown department '{department}'.")
            if group and department and group not in depts[department]["groups"]:
                raise HTTPException(status_code=400, detail=f"Unknown group '{group}'.")
        if not department:
            raise HTTPException(
                status_code=400,
                detail=f"Seat tier '{req.tier}' requires a department.",
            )

    ident = request.client.host if request.client else "login"
    if not security.check_rate_limit(f"login:{ident}"):
        raise HTTPException(status_code=429, detail="Too many sign-in attempts. Try again shortly.")

    access = orgmodel.derive_access(req.tier, department, group)
    label = orgmodel.seat_label(req.tier, access["department"], access["group"])
    issued = security.create_key(
        label=f"{label} session",
        role=label,
        clearance=access["clearance"],
        admin_tier=access["tier"],
        department=access["department"],
        group=access["group"],
        permissions=access["permissions"],
    )
    return {
        "apiKey": issued["apiKey"],
        "role": label,
        "label": label,
        "description": _TIER_DESCRIPTIONS.get(req.tier, ""),
        "permissions": sorted(access["permissions"]),
        "clearance": access["clearance"],
        "adminTier": access["tier"],
        "department": access["department"],
        "group": access["group"],
    }


@app.get("/api/me")
async def me(principal: Principal = Depends(get_principal)) -> dict:
    """The current caller's resolved identity, seat scope, and permissions."""
    return {
        "role": principal.role,
        "label": principal.label,
        "authenticated": principal.authenticated,
        "permissions": sorted(principal.permissions),
        "clearance": principal.clearance,
        "adminTier": principal.admin_tier,
        "department": principal.department,
        "group": principal.group,
    }


@app.post("/api/keys")
async def create_key(
    req: CreateKeyRequest, principal: Principal = Depends(get_principal)
) -> dict:
    """Mint a new API key for a role. Returns the plaintext key ONCE."""
    require(principal, "manage:keys")
    try:
        return security.create_key(req.label, req.role)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


class MintSeatRequest(BaseModel):
    tier: str
    department: str | None = None
    group: str | None = None
    label: str | None = None
    workspaceId: str | None = None


@app.post("/api/seats/mint")
async def mint_seat(
    req: MintSeatRequest, principal: Principal = Depends(get_principal)
) -> dict:
    """Scoped seat provisioning: an administrator mints a revocable seat key for a
    teammate. A System Administrator can mint any seat; a Department/Group admin is
    confined to their own department and cannot mint a seat at or above their own
    authority (no privilege escalation). The plaintext key is returned ONCE."""
    require(principal, "manage:keys")
    if req.tier not in orgmodel.ADMIN_TIERS:
        raise HTTPException(status_code=400, detail=f"Unknown seat tier '{req.tier}'.")

    is_system = principal.admin_tier == "system" or "*" in principal.permissions
    target = orgmodel.derive_access(req.tier, req.department, req.group)

    if not is_system:
        if principal.department and target["department"] != principal.department:
            raise HTTPException(
                status_code=403,
                detail=f"You can only mint seats within {principal.department}.",
            )
        if orgmodel.tier_rank(req.tier) >= orgmodel.tier_rank(principal.admin_tier):
            raise HTTPException(
                status_code=403,
                detail="You cannot mint a seat at or above your own authority level.",
            )

    label = req.label or orgmodel.seat_label(req.tier, target["department"], target["group"])
    issued = security.create_key(
        label=label,
        role=label,
        clearance=target["clearance"],
        admin_tier=target["tier"],
        department=target["department"],
        group=target["group"],
        permissions=target["permissions"],
    )
    _persist_audit(
        [governance.create_audit_event(
            "seat_key_minted",
            f"{principal.role} minted a '{label}' seat key"
            + (f" for {target['department']}" if target["department"] else ""),
            actor=principal.label,
        )],
        req.workspaceId,
    )
    return {
        "apiKey": issued["apiKey"],
        "label": label,
        "tier": target["tier"],
        "department": target["department"],
        "group": target["group"],
        "clearance": target["clearance"],
    }


@app.get("/api/keys")
async def list_keys(principal: Principal = Depends(get_principal)) -> dict:
    require(principal, "manage:keys")
    return {"keys": security.list_keys()}


@app.delete("/api/keys/{key_id}")
async def revoke_key(key_id: int, principal: Principal = Depends(get_principal)) -> dict:
    require(principal, "manage:keys")
    return {"revoked": security.revoke_key(key_id)}


@app.get("/api/metrics")
async def get_metrics(principal: Principal = Depends(get_principal)) -> dict:
    """LLM usage/cost/latency telemetry."""
    require(principal, "view:audit")
    return telemetry.snapshot()


class QueryRequest(BaseModel):
    project: dict
    query: dict


@app.get("/api/schema")
async def get_schema(principal: Principal = Depends(get_principal)) -> dict:
    """The internal database schema (tables + columns) available for structured queries."""
    require(principal, "read:connectors:aggregated")
    return {"tables": database.schema_for()}


@app.post("/api/query")
async def query_data(
    req: QueryRequest, principal: Principal = Depends(get_principal)
) -> dict:
    """Governed database access layer: run a structured, read-only, PII-masked query
    against a project's internal connectors (CRM/ERP/ticketing)."""
    require(principal, "read:connectors:aggregated")
    _validate_project(req.project)
    try:
        result = database.run_query(req.project["connectors"], req.query)
    except database.QueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    _persist_audit(
        governance.build_audit_events(["connector_query_executed"],
                                      f"structured query on {result['table']}"),
        req.project.get("id"),
    )
    return result


@app.get("/api/compliance")
async def get_compliance() -> dict:
    """Regulatory control mappings (GDPR/HIPAA/PCI/SOC2/AML/EU-AI-Act)."""
    return compliance.report()


@app.get("/api/evals")
async def get_evals(
    judge: bool = False, principal: Principal = Depends(get_principal)
) -> dict:
    """Run the golden-set evaluation harness. Deterministic by default; pass
    ``judge=true`` to add an LLM-as-judge quality pass per case."""
    require(principal, "view:audit", "use:assistant")
    from evaluation import evals
    if judge:
        return await evals.run_evals_judged()
    return evals.run_evals()


class BriefingRequest(BaseModel):
    project: dict


@app.post("/api/briefing")
async def briefing_endpoint(
    req: BriefingRequest, principal: Principal = Depends(get_principal)
) -> dict:
    """Persona-aware executive briefing: role-scoped narrative, KPIs, and a ranked
    Next Best Actions list. Internal data sections are gated by RBAC."""
    require(principal, "use:assistant")
    _validate_project(req.project)
    from agentic import briefing
    return await briefing.build_briefing(req.project, principal.permissions, principal.role)


@app.post("/api/conversations/{session_id}/validate")
async def validate_conversation(
    session_id: str, principal: Principal = Depends(get_principal)
) -> dict:
    """LLM-judge validation of a stored conversation: grades each assistant turn
    for groundedness, relevance, and PII safety against the project's data."""
    require(principal, "view:audit", "use:assistant")
    from evaluation import convvalidate
    report = await convvalidate.validate_session(session_id)
    summary = report.get("summary", {})
    failed = summary.get("available") and summary.get("passed", 0) < summary.get("judged", 0)
    audit_type = "guardrail_triggered" if failed else "assistant_answered"
    msg = (
        f"Conversation {session_id} validated: "
        f"{summary.get('passed', 0)}/{summary.get('judged', 0)} turns passed."
    )
    _persist_audit(
        [governance.create_audit_event(audit_type, msg, actor="judge")],
        report.get("projectId"),
    )
    return report


@app.get("/api/projects")
async def list_projects(principal: Principal = Depends(get_principal)) -> dict:
    require(principal, "view:audit", "read:knowledge")
    return {"projects": appstore.list_projects()}


@app.get("/api/projects/{project_id}")
async def get_project(project_id: str, principal: Principal = Depends(get_principal)) -> dict:
    require(principal, "read:knowledge")
    project = appstore.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


@app.delete("/api/projects/{project_id}")
async def delete_project(
    project_id: str, principal: Principal = Depends(get_principal)
) -> dict:
    """Right-to-erasure: purge a project and its conversation memory."""
    require(principal, "manage:connectors", "write:all")
    result = appstore.delete_project(project_id)
    # Record the erasure itself in the (retained) audit trail for accountability.
    _persist_audit(
        governance.build_audit_events(["data_erased"], f"project {project_id}"),
        project_id,
    )
    return result


@app.get("/api/memory/{session_id}")
async def get_memory(session_id: str, principal: Principal = Depends(get_principal)) -> dict:
    require(principal, "use:assistant")
    return {"turns": appstore.get_turns(session_id, limit=50)}


@app.delete("/api/memory/{session_id}")
async def clear_memory(session_id: str, principal: Principal = Depends(get_principal)) -> dict:
    require(principal, "use:assistant")
    return {"cleared": appstore.clear_session(session_id)}
