"""LLM client for StackLaunch.

Primary provider is SovereignEG (https://sovereigneg.com), an OpenAI-compatible,
Egypt-billed inference API. If no key is configured, we fall back to a local
Ollama instance (also OpenAI-compatible) so the app still works fully offline.
Everything degrades gracefully: if no LLM is reachable, callers get None and use
heuristic fallbacks.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from openai import AsyncOpenAI

from core import telemetry

# Industry taxonomy — MUST match the frontend IndustryKey union + labels.
INDUSTRY_LABELS: dict[str, str] = {
    "transport": "Transport / Intercity Bus",
    "banking": "Banking / Financial Services",
    "retail": "Retail / E-commerce",
    "healthcare": "Healthcare / Clinics",
    "real_estate": "Real Estate / Property",
    "telecom": "Telecom / Mobile Operator",
    "education": "Education / Training",
    "hospitality": "Hospitality / Hotels",
    "insurance": "Insurance",
    "technology": "Technology / Software & AI Services",
    "generic_services": "General Services",
}


@dataclass
class Provider:
    name: str
    base_url: str
    api_key: str
    model: str


def _resolve_provider() -> Provider | None:
    api_key = os.getenv("LLM_API_KEY", "").strip()
    if api_key:
        return Provider(
            name="sovereigneg",
            base_url=os.getenv("LLM_BASE_URL", "https://sovereigneg.com/v1"),
            api_key=api_key,
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        )
    # Fall back to local Ollama if it's running.
    ollama = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    try:
        root = ollama.replace("/v1", "")
        httpx.get(f"{root}/api/tags", timeout=1.5)
    except httpx.HTTPError:
        return None
    return Provider(
        name="ollama",
        base_url=ollama,
        api_key="ollama",
        model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
    )


_provider = _resolve_provider()
_client = (
    AsyncOpenAI(base_url=_provider.base_url, api_key=_provider.api_key, timeout=60.0)
    if _provider
    else None
)


def provider_info() -> dict:
    if not _provider:
        return {"enabled": False, "provider": None, "model": None, "host": None}
    host = urlparse(_provider.base_url).hostname
    return {
        "enabled": True,
        "provider": _provider.name,
        "model": _provider.model,
        "host": host,
    }


def is_enabled() -> bool:
    return _client is not None


def _extract_json(text: str) -> dict | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


async def _chat(messages: list[dict], *, json_mode: bool = False, max_tokens: int = 700) -> str | None:
    if not _client or not _provider:
        return None
    kwargs: dict = {"model": _provider.model, "messages": messages, "temperature": 0.2,
                    "max_tokens": max_tokens}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    with telemetry.timer() as t:
        try:
            resp = await _client.chat.completions.create(**kwargs)
        except Exception:
            # Retry once without json_mode (some models reject response_format).
            if json_mode:
                try:
                    kwargs.pop("response_format", None)
                    resp = await _client.chat.completions.create(**kwargs)
                except Exception:
                    telemetry.record(_provider.model, 0, 0, t.ms, error=True)
                    return None
            else:
                telemetry.record(_provider.model, 0, 0, t.ms, error=True)
                return None
    _record_usage(resp, t.ms)
    return resp.choices[0].message.content


def _record_usage(resp, latency_ms: float) -> None:
    usage = getattr(resp, "usage", None)
    pt = getattr(usage, "prompt_tokens", 0) or 0
    ct = getattr(usage, "completion_tokens", 0) or 0
    telemetry.record(getattr(resp, "model", _provider.model if _provider else "unknown"),
                     pt, ct, latency_ms)


async def classify_site(
    *, url: str, company_hint: str, text: str, search_context: str = ""
) -> dict | None:
    """Use the LLM to extract the company name, a description, and the industry."""
    options = "\n".join(f"- {k}: {v}" for k, v in INDUSTRY_LABELS.items())
    content = text[:6000]
    extra = f"\n\nAdditional web search context:\n{search_context[:2000]}" if search_context else ""
    system = (
        "You are an analyst that classifies a company from its website content. "
        "Respond ONLY with a compact JSON object, no prose."
    )
    user = (
        f"Website: {url}\n"
        f"Detected name hint: {company_hint}\n\n"
        f"Website content:\n{content}{extra}\n\n"
        "Return JSON with exactly these keys:\n"
        '{\n'
        '  "company_name": string,            // the real, properly-cased company name\n'
        '  "description": string,             // one or two sentences on what they do\n'
        '  "industry_key": one of these keys,\n'
        '  "confidence": number,              // 0..1\n'
        '  "topics": string[]                 // up to 6 key offerings/topics\n'
        "}\n\n"
        f"Valid industry_key values:\n{options}\n"
        "Pick generic_services only if nothing else fits."
    )
    raw = await _chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        json_mode=True,
        max_tokens=500,
    )
    if not raw:
        return None
    data = _extract_json(raw)
    if not data:
        return None
    key = str(data.get("industry_key", "generic_services"))
    if key not in INDUSTRY_LABELS:
        key = "generic_services"
    try:
        confidence = float(data.get("confidence", 0.7))
    except (TypeError, ValueError):
        confidence = 0.7
    topics = data.get("topics") or []
    if not isinstance(topics, list):
        topics = []
    return {
        "company_name": str(data.get("company_name") or company_hint).strip(),
        "description": str(data.get("description") or "").strip(),
        "industry_key": key,
        "industry_label": INDUSTRY_LABELS[key],
        "confidence": max(0.0, min(1.0, confidence)),
        "topics": [str(t).strip() for t in topics][:6],
    }


_PROFILE_ENTITY_TYPES = {
    "product", "service", "plan", "branch", "store", "route",
    "facility", "program", "property", "policy", "department",
}


async def extract_data_profile(
    *,
    company: str,
    industry_label: str,
    url: str,
    text: str,
    topics: "list[str] | None" = None,
) -> dict | None:
    """Extract a grounded 'data profile' from the real website.

    The synthetic CRM / ERP / ticketing datasets are otherwise built from generic
    industry templates. This grounds their *vocabulary* (the company's real
    products/services, customer segments, locations, support categories) and a
    rough numeric *scale* in the actual site, so the demo data feels like it
    belongs to this specific company. The individual numbers are still generated
    deterministically downstream — we only ask the model for labels and ranges.

    Returns a normalised dict, or None if no LLM is reachable / output is unusable.
    """
    topic_line = ("\nKey topics: " + ", ".join(topics[:8])) if topics else ""
    allowed = ", ".join(sorted(_PROFILE_ENTITY_TYPES))
    system = (
        "You extract a structured 'data profile' for a company from its website so a "
        "demo CRM/ERP/ticketing dataset can be grounded in the company's REAL offerings. "
        "Respond ONLY with a compact JSON object, no prose. Use ONLY names that are "
        "plausible for THIS company based on the content; never invent unrelated brands."
    )
    user = (
        f"Company: {company}\n"
        f"Industry: {industry_label}\n"
        f"Website: {url}{topic_line}\n\n"
        f"Website content:\n{text[:6000]}\n\n"
        "Return JSON with exactly these keys:\n"
        "{\n"
        '  "segments": string[],          // 3-6 customer segments this company tracks\n'
        '  "cities": string[],            // 4-10 cities/regions it operates in (real if named)\n'
        '  "products": [                  // 8-16 of the company\'s real products/services/locations\n'
        f'     {{"entity_type": one of [{allowed}], "name": string}}\n'
        "  ],\n"
        '  "ticket_categories": string[], // 5-8 realistic support ticket categories\n'
        '  "currency": string,            // ISO currency code billed in, e.g. "EGP", "USD"\n'
        '  "scale": {                     // rough magnitudes so demo numbers feel proportionate\n'
        '     "ltv": [min, max],          // typical customer lifetime value range\n'
        '     "monthly_revenue": [min, max] // typical per-product monthly revenue range\n'
        "  }\n"
        "}\n"
        "Prefer specifics drawn from the website (named plans, product lines, branches). "
        "Keep every name short (<= 40 chars). Bigger, well-known companies should get "
        "larger scale ranges; small local businesses smaller ones."
    )
    raw = await _chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        json_mode=True,
        max_tokens=800,
    )
    if not raw:
        return None
    data = _extract_json(raw)
    if not data:
        return None
    return _normalise_profile(data)


def _norm_str_list(value, max_items: int, max_len: int = 40) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        s = str(item).strip()
        if not s or len(s) > max_len:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= max_items:
            break
    return out


def _norm_range(value, lo_bound: int, hi_bound: int) -> "list[int] | None":
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        lo, hi = int(value[0]), int(value[1])
    except (TypeError, ValueError):
        return None
    lo = max(lo_bound, min(lo, hi_bound))
    hi = max(lo_bound, min(hi, hi_bound))
    if hi <= lo:
        return None
    return [lo, hi]


def _normalise_profile(data: dict) -> "dict | None":
    products_raw = data.get("products") or []
    products: list[dict] = []
    seen: set[str] = set()
    if isinstance(products_raw, list):
        for p in products_raw:
            if not isinstance(p, dict):
                continue
            name = str(p.get("name") or "").strip()
            if not name or len(name) > 40:
                continue
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            etype = str(p.get("entity_type") or "product").strip().lower()
            if etype not in _PROFILE_ENTITY_TYPES:
                etype = "product"
            products.append({"entity_type": etype, "name": name})
            if len(products) >= 16:
                break

    segments = _norm_str_list(data.get("segments"), 6)
    cities = _norm_str_list(data.get("cities"), 10)
    ticket_categories = _norm_str_list(data.get("ticket_categories"), 8)

    scale_raw = data.get("scale") if isinstance(data.get("scale"), dict) else {}
    scale: dict[str, list[int]] = {}
    ltv = _norm_range(scale_raw.get("ltv"), 100, 5_000_000)
    rev = _norm_range(scale_raw.get("monthly_revenue"), 1_000, 500_000_000)
    if ltv:
        scale["ltv"] = ltv
    if rev:
        scale["monthly_revenue"] = rev

    currency = str(data.get("currency") or "").strip().upper()[:4] or "EGP"

    # Useless unless we grounded at least the offerings or the segments.
    if not products and not segments:
        return None

    return {
        "currency": currency,
        "segments": segments,
        "cities": cities,
        "products": products,
        "ticket_categories": ticket_categories,
        "scale": scale,
    }


async def answer(*, question: str, company: str, context: str) -> str | None:
    """RAG-style answer grounded in the supplied context (website + data summary)."""
    system = (
        f"You are the governed AI assistant for {company}. Answer ONLY using the "
        "context provided (website knowledge, internal data summaries, and any web "
        "search results). If the answer is not in the context, say so plainly. "
        "Never invent specific numbers. When you reference individual customers, use "
        "IDs and segments only — never names, emails, or phone numbers. Be concise "
        "and concrete, and cite page titles or URLs from the context when relevant."
    )
    user = f"Context:\n{context[:9000]}\n\nQuestion: {question}"
    return await _chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=700,
    )


def supports_tools() -> bool:
    return _client is not None


async def chat_with_tools(
    messages: list[dict],
    tools: list[dict],
    *,
    temperature: float = 0.2,
    max_tokens: int = 900,
) -> dict | None:
    """One tool-calling turn.

    Returns a normalised dict ``{"content": str | None, "tool_calls": [...]}`` where
    each tool call is ``{"id", "name", "arguments": dict}`` with arguments already
    JSON-parsed. Returns None if no LLM is configured or the call fails, so the
    agent loop can fall back to deterministic answering.
    """
    if not _client or not _provider:
        return None
    with telemetry.timer() as t:
        try:
            resp = await _client.chat.completions.create(
                model=_provider.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception:
            telemetry.record(_provider.model, 0, 0, t.ms, error=True)
            return None
    _record_usage(resp, t.ms)

    msg = resp.choices[0].message
    tool_calls = []
    for tc in (msg.tool_calls or []):
        raw_args = getattr(tc.function, "arguments", "") or "{}"
        parsed = _extract_json(raw_args) if isinstance(raw_args, str) else raw_args
        tool_calls.append(
            {"id": tc.id, "name": tc.function.name, "arguments": parsed or {}}
        )
    return {"content": msg.content, "tool_calls": tool_calls}
