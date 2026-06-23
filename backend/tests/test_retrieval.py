"""Tests for BM25 retrieval with citations (retrieval.py)."""

from agentic import retrieval

PAGES = [
    {"title": "Personal Loans", "url": "https://b.com/loans",
     "content": "We offer personal loans with low interest rates. Apply online for a personal loan "
                "and get approval within 24 hours. Our loan products suit many needs."},
    {"title": "Branches", "url": "https://b.com/branches",
     "content": "Find our branches across Cairo and Alexandria. Visit a branch near you for in-person help. "
                "Branch opening hours vary by location."},
]


def test_ranks_relevant_page_first():
    cites = retrieval.search(PAGES, "where can I get a personal loan?", top_k=3)
    assert cites
    assert "Loans" in cites[0].title


def test_returns_citation_offsets():
    cites = retrieval.search(PAGES, "branch hours", top_k=3)
    assert cites
    top = cites[0]
    assert top.start >= 0
    assert top.end > top.start
    # The offsets point at a real span of the page content.
    page = next(p for p in PAGES if p["url"] == top.url)
    assert page["content"][top.start:top.end].strip() != ""


def test_empty_query_returns_nothing():
    assert retrieval.search(PAGES, "the a is of") == []


def test_no_pages_returns_nothing():
    assert retrieval.search([], "loan") == []
