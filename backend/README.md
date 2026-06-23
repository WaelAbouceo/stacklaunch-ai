# StackLaunch API (FastAPI)

This service is the **single brain** of the product — the browser only renders.
It owns all business logic:

- **Crawl** an arbitrary website (httpx + BeautifulSoup).
- **Search fallback** via self-hosted **SearXNG** when a site is unreachable
  (e.g. TLS-blocked) or returns too little content.
- **LLM reasoning** via [SovereignEG](https://sovereigneg.com) (OpenAI-compatible),
  with automatic fallback to local **Ollama** when no key is configured.
- **Industry taxonomy + classification** (`industries.py`).
- **Internal demo-data generation** — CRM / ERP / ticketing (`datagen.py`, `rng.py`).
- **Analytics** — connector + cross-source summaries (`analytics.py`).
- **Governance** — guardrails, roles, audit, observability (`governance.py`).
- **Assistant** — intent classification, grounded answers, PII policy (`assistant.py`).
- **Project assembly** (`projectbuilder.py`).

## Run

```bash
# 1) SearXNG (search fallback)
docker compose up -d                 # http://localhost:8080

# 2) API
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                 # add LLM_API_KEY (or leave blank for Ollama)
uvicorn main:app --reload --port 8000
```

## Endpoints

- `GET /api/health` → `{ status, llm: {enabled, provider, model}, searxng }`
- `GET /api/industries` → `{ industries: [{ key, label }] }` (dropdown taxonomy).
- `POST /api/scan` `{ "url": "cibeg.com" }` → real scan + LLM classification:
  `companyName`, `siteSummary`, `industry`/`industryLabel`/`industryConfidence`,
  `knowledgeBase.pages[]`, `usedSearch`, `crawlFailed`, `llm`.
- `POST /api/build` `{ websiteUrl, companyName, industry, scan }` → the full
  governed **Project**: generated CRM/ERP/ticketing connectors, precomputed
  `analytics` (cross-source summary), `suggestedQuestions`, `apiKey`, guardrails,
  roles, audit, and observability. `scan` is the `/api/scan` payload (no re-crawl).
- `POST /api/ask` `{ question, project, allowSearch }` → the full assistant result
  computed server-side: `{ content, sources, computedFrom, guardrailNote,
  observabilityDelta, auditEvents, usedSearch }`. Intent classification, guardrails,
  PII policy, and metrics all run here; the LLM answer is grounded in the project's
  pages + PII-safe data summary, augmented with SearXNG when knowledge is thin.
- `POST /api/agent` `{ question, project, allowSearch, maxSteps }` → **agentic**
  answer. Instead of a single shot, the model calls governed **tools** (`tools.py`)
  — `get_company_overview`, `search_knowledge_base`, `get_crm/erp/ticketing_summary`,
  `get_cross_source_insights`, `list_at_risk_customers` (PII-masked), `web_search` —
  in a loop (`agent.py`), then answers grounded in the tool results. Returns the same
  governance shape as `/api/ask` plus `toolsUsed` and `mode` (`agent` or
  `fallback:<reason>`). Sources, observability deltas, and audit events are derived
  from the tools actually invoked. Falls back to the deterministic assistant when no
  LLM is configured.
- `POST /api/agent/stream` — same input, **Server-Sent Events**: streams `step`,
  `tool_call`, `tool_result`, `final` (and `error`) events as JSON `data:` lines.
- `GET /api/audit?limit=&projectId=` → the persisted, **hash-chained** audit trail
  (newest first): `{ seq, id, projectId, type, message, actor, timestamp, prevHash,
  hash }`.
- `GET /api/audit/verify` → `{ ok, count, brokenAtSeq, signaturesOk }` — recomputes
  the chain to prove the log hasn't been tampered with.
- `POST /api/orchestrate` `{ question, project, allowSearch, maxSteps }` →
  **multi-agent** answer. A Supervisor delegates to least-privilege specialists
  (Knowledge: KB + web; Data: CRM/ERP/ticketing), then synthesises with a PII
  compliance pass. Returns `specialistsUsed` + the usual governance shape.
- `GET /api/roles` → roles + permissions. `POST /api/keys` `{label, role}` →
  mints an API key (plaintext shown once); `GET /api/keys`, `DELETE /api/keys/{id}`.
- `GET /api/metrics` → LLM telemetry `{ calls, totalTokens, estimatedCostUsd,
  avgLatencyMs, byModel }`.
- `GET /api/schema` → internal database schema (tables + columns).
- `POST /api/query` `{ project, query }` → **governed database access layer**: runs a
  structured, read-only, PII-masked query against the project's connectors and
  returns `{ table, columns, rowCount, rows, sql }`. The `query` is a validated spec
  (`{table, select, aggregate, filters, group_by, order_by, limit}`) — never raw SQL.
  The agent can also do this itself via the `query_internal_data` tool, so the LLM
  extracts structured data on demand.
- `GET /api/compliance` → regulatory control mappings (GDPR/HIPAA/PCI/SOC2/AML/
  EU-AI-Act) with `coverageByRegulation`.
- `GET /api/evals` → runs the golden-set eval harness `{ passed, total, passRate }`.
- `GET/DELETE /api/projects[/{id}]` → list/fetch/erase persisted projects
  (DELETE = right-to-erasure). `GET/DELETE /api/memory/{sessionId}` → conversation
  memory. Pass `sessionId` to `/api/agent` to enable memory.

## Security & RBAC

- **Auth** (`security.py`): real, revocable API keys (SHA-256 hashed in SQLite).
  Send `X-API-Key`. Enforced only when `REQUIRE_AUTH=1`; otherwise callers are the
  Owner role so the demo keeps working. Per-identity **rate limiting** + CORS
  locked to `ALLOWED_ORIGINS`.
- **RBAC** (`rbac.py`): roles → permissions, enforced on both endpoints and
  individual **tool calls** inside the agent (an unauthorised tool is denied and
  surfaced to the model as a governance refusal, bumping `guardrailBlocks`).
- **Prompt-injection** (`guardrails.py`): crawled + web text is quarantined
  (trigger phrases defanged, wrapped as untrusted data) before reaching the model.
- **Retrieval** (`retrieval.py`): BM25 over page chunks with **citation offsets**.

## Enforced governance (not just declarative)

- **PII redaction (`pii.py`)** — deterministic, regex + key-aware redaction of email,
  phone, payment card, IBAN, US SSN, and Egyptian national ID. Enforced in the agent
  loop both ways: tool results are scrubbed **before** reaching the model (the main
  prompt-injection / leak surface for crawled + web text), and the final answer is
  scrubbed **after**. Redactions increment `piiMaskingEvents` and emit a
  `pii_masking_applied` audit event.
- **Tamper-evident audit (`auditstore.py`)** — every audit event is appended to a
  local SQLite file in a SHA-256 hash chain (`hash = sha256(prev_hash + canonical)`).
  Altering or deleting any historical row breaks every later hash;
  `/api/audit/verify` pinpoints the first broken `seq`. Persisted from `/api/build`,
  `/api/ask`, and the agent endpoints. DB path via `AUDIT_DB_PATH` (default
  `backend/audit.db`, git-ignored).

## Agent tools (governed data-access layer)

Tools are the only way the agent reaches data — raw records never enter the prompt.
Each tool carries its own `sources`, `observability` delta, and `audit_types`, so
governance is accumulated from real tool usage rather than guessed from a regex
intent. PII masking (e.g. `list_at_risk_customers`) is enforced inside the tool.

```bash
pip install -r requirements-dev.txt   # adds pytest
pytest -q                             # tools + agent loop tests (scripted fake LLM)
```

## Files

- `industries.py` — industry taxonomy, demo-data shaping, suggested questions.
- `rng.py` / `datagen.py` — seeded PRNG + CRM/ERP/ticketing generation.
- `analytics.py` — connector + cross-source summaries.
- `governance.py` — guardrails, roles, audit, observability.
- `assistant.py` — intent classification + governance metadata + fallback answers.
- `tools.py` — governed tool registry (the agent's data-access layer).
- `agent.py` — tool-calling agent loop (ReAct-style) with streaming + fallback.
- `orchestrator.py` — multi-agent supervisor over specialist sub-agents.
- `pii.py` — deterministic PII/PHI detection + redaction (enforced guardrail).
- `guardrails.py` — prompt-injection detection + quarantine of untrusted text.
- `retrieval.py` — BM25 retrieval with citation offsets.
- `database.py` — governed data-access layer: in-memory SQLite over connectors +
  safe structured-query compiler (read-only, schema-validated, PII-masked).
- `auditstore.py` — SQLite hash-chained, HMAC-signed, tamper-evident audit log.
- `security.py` — API-key auth, key management, rate limiting.
- `rbac.py` — role/permission model + enforcement helpers.
- `appstore.py` — SQLite persistence for projects + conversation memory (+ erasure).
- `telemetry.py` — LLM token/cost/latency metrics.
- `compliance.py` — regulatory control mappings.
- `evals.py` — golden-set evaluation harness.
- `config.py` — central config + shared time source.
- `projectbuilder.py` — assembles the governed Project.
- `scanner.py` — crawl + SearXNG fallback orchestration.
- `search.py` — SearXNG JSON client.
- `llm.py` — provider resolution (SovereignEG → Ollama) + classify/answer.
- `main.py` — FastAPI app wiring all of the above.
- `docker-compose.yml` + `searxng/settings.yml` — local SearXNG.
