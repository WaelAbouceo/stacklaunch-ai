# StackLaunch AI

Turn any website into a governed enterprise AI stack demo.

A **full-stack, LLM-driven, data-sovereign** app:

- **Frontend** (React + TypeScript + Vite) — the UI, governance, dashboards, and assistant chat.
- **Backend** (`backend/`, FastAPI) — crawls the requested site, falls back to
  **SearXNG** search when a site can't be reached, and runs **LLM** reasoning for
  industry classification and the RAG assistant.
- **LLM**: [SovereignEG](https://sovereigneg.com) (OpenAI-compatible, Egypt-billed).
  Falls back to local **Ollama** automatically when no key is set.
- **Search**: self-hosted **SearXNG** (Docker).

## What's real vs. generated

| Part | Source |
| --- | --- |
| Website crawl, company name, description, pages | **Real** — scraped live, or via SearXNG when the site is unreachable |
| Industry classification | **Real LLM** — classified from the real content |
| Knowledge base | **Real** — the actual pages we indexed |
| Assistant answers | **Real LLM (RAG)** — grounded in the pages + a PII-safe data summary, with SearXNG fallback |
| CRM / ERP / Ticketing datasets | **Generated** — private internal systems we can't crawl |

## Flow

1. Enter a URL → **"Check website"**.
2. Backend crawls it (or searches via SearXNG if blocked), then the LLM extracts
   the real company name, description, and industry. A **confirmation screen**
   shows what we understood (e.g. `cib.com` → corrected to CIB / Banking). Fix
   the URL or industry if needed.
3. Confirm → generate the governed stack and open the dashboard + LLM assistant.

## Run (three processes)

### 1. SearXNG (search fallback)

```bash
cd backend
docker compose up -d        # serves http://localhost:8080
```

### 2. Backend (FastAPI + LLM)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env         # then add your SovereignEG key (or leave blank for Ollama)
uvicorn main:app --reload --port 8000
```

Check `GET http://localhost:8000/api/health` — it reports the active LLM provider
and whether SearXNG is reachable.

### 3. Frontend (Vite)

```bash
npm install
npm run dev                  # http://localhost:5173, proxies /api -> :8000
```

## Configuration (`backend/.env`)

```
LLM_BASE_URL=https://sovereigneg.com/v1
LLM_API_KEY=sk-...           # from sovereigneg.com; blank => use local Ollama
LLM_MODEL=gpt-4o-mini        # any id from the SovereignEG catalog
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen2.5:7b
SEARXNG_URL=http://localhost:8080
```

The app degrades gracefully: no LLM → keyword industry detection + templated
answers; no SearXNG → direct-crawl only.
