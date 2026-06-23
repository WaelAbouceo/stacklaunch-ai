"""Lightweight semantic-ish retrieval with citations (BM25 over page chunks).

Upgrades the previous keyword-frequency scoring to **BM25** (the standard lexical
ranking function: term frequency saturation + inverse document frequency + length
normalisation) over *chunked* page content, and returns **citations with character
offsets** so every retrieved snippet is traceable back to an exact span of a real
crawled page — important for grounding claims in a regulated setting.

Pure Python, no external dependencies (honours the "lightweight, no heavy infra"
constraint). A true embedding model would rank higher on semantics, but BM25 with
citations is a large, dependency-free step up from raw keyword counts.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from agentic.assistant import STOPWORDS

_TOKEN = re.compile(r"[a-z0-9]+")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")

K1 = 1.5
B = 0.75
MIN_CHUNK_CHARS = 160
MAX_CHUNK_CHARS = 480


@dataclass
class Chunk:
    page_index: int
    title: str
    url: str
    text: str
    start: int  # char offset within the page's content
    end: int


@dataclass
class Citation:
    title: str
    url: str
    snippet: str
    score: float
    start: int
    end: int


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if len(t) > 2 and t not in STOPWORDS]


def _chunk_page(page_index: int, page: dict) -> list[Chunk]:
    title = page.get("title", "")
    url = page.get("url", "")
    content = (page.get("content") or page.get("summary") or "").strip()
    if not content:
        return []
    chunks: list[Chunk] = []
    pos = 0
    buf = ""
    buf_start = 0
    for sent in _SENT_SPLIT.split(content):
        if not buf:
            buf_start = content.find(sent, pos)
            if buf_start < 0:
                buf_start = pos
        buf = (buf + " " + sent).strip() if buf else sent
        pos = buf_start + len(buf)
        if len(buf) >= MIN_CHUNK_CHARS:
            text = buf[:MAX_CHUNK_CHARS]
            chunks.append(Chunk(page_index, title, url, text, buf_start, buf_start + len(text)))
            buf = ""
    if buf:
        chunks.append(Chunk(page_index, title, url, buf, buf_start, buf_start + len(buf)))
    return chunks


def build_chunks(pages: list[dict]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for i, page in enumerate(pages):
        chunks.extend(_chunk_page(i, page))
    return chunks


def search(pages: list[dict], query: str, top_k: int = 4) -> list[Citation]:
    """Rank page chunks against the query with BM25; return citations with offsets."""
    chunks = build_chunks(pages)
    if not chunks:
        return []
    q_terms = _tokenize(query)
    if not q_terms:
        return []

    docs = [_tokenize(c.text) for c in chunks]
    doc_lens = [len(d) for d in docs]
    avgdl = (sum(doc_lens) / len(doc_lens)) or 1.0
    n = len(docs)

    # Document frequency per query term.
    df: dict[str, int] = {}
    for term in set(q_terms):
        df[term] = sum(1 for d in docs if term in d)

    scored: list[Citation] = []
    for c, d, dl in zip(chunks, docs, doc_lens):
        if not d:
            continue
        score = 0.0
        for term in q_terms:
            f = d.count(term)
            if f == 0:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            denom = f + K1 * (1 - B + B * dl / avgdl)
            score += idf * (f * (K1 + 1)) / denom
        if score > 0:
            scored.append(Citation(
                title=c.title, url=c.url, snippet=c.text.strip(),
                score=round(score, 4), start=c.start, end=c.end,
            ))
    scored.sort(key=lambda x: x.score, reverse=True)
    return scored[:top_k]
