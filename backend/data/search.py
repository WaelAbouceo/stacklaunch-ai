"""SearXNG retrieval client.

Used as a fallback source of information when a site can't be crawled directly
(blocked, TLS errors, JS-only) or when the crawl returns too little text.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8080").rstrip("/")
SEARCH_TIMEOUT = 10.0


@dataclass
class SearchResult:
    title: str
    url: str
    content: str

    def to_dict(self) -> dict:
        return {"title": self.title, "url": self.url, "content": self.content}


async def search(query: str, max_results: int = 8) -> list[SearchResult]:
    """Query the local SearXNG instance and return result snippets.

    Returns an empty list (never raises) so callers can treat search as a
    best-effort augmentation.
    """
    params = {"q": query, "format": "json", "safesearch": "0"}
    try:
        async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as client:
            resp = await client.get(f"{SEARXNG_URL}/search", params=params)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError):
        return []

    results: list[SearchResult] = []
    seen: set[str] = set()
    for item in data.get("results", []):
        url = item.get("url") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        results.append(
            SearchResult(
                title=(item.get("title") or "").strip(),
                url=url,
                content=(item.get("content") or "").strip(),
            )
        )
        if len(results) >= max_results:
            break
    return results


async def is_available() -> bool:
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(f"{SEARXNG_URL}/healthz")
            return resp.status_code == 200
    except httpx.HTTPError:
        return False
