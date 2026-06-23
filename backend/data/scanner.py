"""Real website crawler + content extractor.

Fetches the requested site (homepage + a few internal pages), extracts the real
company name, description, page titles and text, and returns a structured result
the frontend can turn into a knowledge base. No mock data here — everything in
the result comes from the live site.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse, urldefrag

import httpx
from bs4 import BeautifulSoup

from data import search
from governance import sovereignty

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 StackLaunchBot/1.0"
)

# How aggressively we crawl. Kept small so a scan stays fast and polite.
MAX_PAGES = 7
PER_REQUEST_TIMEOUT = 8.0
MAX_HTML_BYTES = 2_000_000

# Internal link slugs we prioritise — these usually carry the substantive content.
PRIORITY_HINTS = [
    "about", "about-us", "who-we-are", "company", "what-we-do",
    "services", "service", "products", "product", "solutions",
    "pricing", "plans", "personal", "business", "corporate",
    "features", "platform", "support", "faq", "help", "contact",
]

NAV_NOISE = re.compile(
    r"^(home|menu|login|log in|sign in|sign up|register|search|skip to|"
    r"cookie|accept|subscribe|newsletter|back to top)$",
    re.IGNORECASE,
)


class ScanError(Exception):
    """Raised when the requested site cannot be scanned at all."""


@dataclass
class Page:
    url: str
    title: str
    summary: str
    topics: list[str]
    content: str


@dataclass
class ScanResult:
    website_url: str
    company_name: str
    site_summary: str
    scanned_text: str
    pages: list[Page] = field(default_factory=list)
    used_search: bool = False
    crawl_failed: bool = False

    def to_dict(self) -> dict:
        return {
            "websiteUrl": self.website_url,
            "companyName": self.company_name,
            "siteSummary": self.site_summary,
            "scannedText": self.scanned_text,
            "usedSearch": self.used_search,
            "crawlFailed": self.crawl_failed,
            "knowledgeBase": {
                "pagesIndexed": len(self.pages),
                "pages": [
                    {
                        "url": p.url,
                        "title": p.title,
                        "summary": p.summary,
                        "topics": p.topics,
                        "content": p.content,
                    }
                    for p in self.pages
                ],
            },
        }


def normalize_url(raw: str) -> str:
    url = (raw or "").strip()
    if not url:
        raise ScanError("No URL provided.")
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.netloc:
        raise ScanError(f"'{raw}' is not a valid URL.")
    # Sovereign egress policy: never let a scan target an internal / metadata host.
    try:
        sovereignty.assert_safe_target(url)
    except sovereignty.EgressBlocked as exc:
        raise ScanError(str(exc)) from exc
    return url


def registrable_domain(netloc: str) -> str:
    host = netloc.split(":")[0].lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _soup_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "template", "svg"]):
        tag.decompose()
    return _clean_text(soup.get_text(" "))


def extract_company_name(soup: BeautifulSoup, url: str) -> str:
    # 1) Open Graph / app name are the most reliable.
    for selector in [
        ("meta", {"property": "og:site_name"}),
        ("meta", {"name": "application-name"}),
        ("meta", {"name": "apple-mobile-web-app-title"}),
    ]:
        tag = soup.find(*selector)
        if tag and tag.get("content"):
            name = _clean_text(tag["content"])
            if name:
                return name

    # 2) <title>, stripped of taglines and common suffixes.
    if soup.title and soup.title.string:
        title = _clean_text(soup.title.string)
        parts = re.split(r"\s*[|\-–—:•]\s*", title)
        parts = [p for p in parts if p and not NAV_NOISE.match(p)]
        if parts:
            # Prefer the shortest meaningful chunk (usually the brand).
            candidate = min(parts, key=len)
            candidate = re.sub(
                r"^(welcome to|home|homepage)\s+", "", candidate, flags=re.IGNORECASE
            ).strip()
            if candidate:
                return candidate

    # 3) Fall back to the domain label.
    host = registrable_domain(urlparse(url).netloc)
    label = host.split(".")[0]
    return " ".join(w.capitalize() for w in re.split(r"[-_]", label) if w) or host


def extract_description(soup: BeautifulSoup) -> str:
    for selector in [
        ("meta", {"name": "description"}),
        ("meta", {"property": "og:description"}),
        ("meta", {"name": "twitter:description"}),
    ]:
        tag = soup.find(*selector)
        if tag and tag.get("content"):
            desc = _clean_text(tag["content"])
            if len(desc) > 20:
                return desc

    # Fall back to the first substantial paragraph.
    for p in soup.find_all("p"):
        text = _clean_text(p.get_text(" "))
        if len(text) > 60:
            return text
    return ""


def extract_topics(soup: BeautifulSoup) -> list[str]:
    topics: list[str] = []
    seen: set[str] = set()
    for tag in soup.find_all(["h1", "h2", "h3"]):
        text = _clean_text(tag.get_text(" "))
        if not text or len(text) > 80 or NAV_NOISE.match(text):
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        topics.append(text)
        if len(topics) >= 8:
            break
    return topics


def discover_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    base_host = registrable_domain(urlparse(base_url).netloc)
    prioritized: list[str] = []
    others: list[str] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute, _ = urldefrag(urljoin(base_url, href))
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue
        if registrable_domain(parsed.netloc) != base_host:
            continue
        # Skip obvious file downloads.
        if re.search(r"\.(pdf|jpg|jpeg|png|gif|svg|zip|mp4|webp|ico)$", parsed.path, re.IGNORECASE):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        slug = parsed.path.lower()
        if any(hint in slug for hint in PRIORITY_HINTS):
            prioritized.append(absolute)
        else:
            others.append(absolute)

    return prioritized + others


async def _egress_guard(request: httpx.Request) -> None:
    """httpx request hook: enforce the egress policy on every hop, including
    redirect targets that bypass a pre-request URL check."""
    if not sovereignty.is_safe_target(str(request.url)):
        raise httpx.RequestError(
            f"Egress blocked: {request.url.host}", request=request
        )


async def fetch(client: httpx.AsyncClient, url: str) -> tuple[str, str] | None:
    # Re-check every link we follow, not just the entry URL — discovered links and
    # redirects must obey the same egress policy.
    if not sovereignty.is_safe_target(url):
        return None
    try:
        resp = await client.get(url, timeout=PER_REQUEST_TIMEOUT)
    except (httpx.HTTPError, httpx.InvalidURL):
        return None
    if resp.status_code >= 400:
        return None
    content_type = resp.headers.get("content-type", "")
    if "html" not in content_type.lower():
        return None
    html = resp.text[:MAX_HTML_BYTES]
    return str(resp.url), html


def build_page(url: str, html: str) -> Page:
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    if soup.title and soup.title.string:
        title = _clean_text(soup.title.string)
    if not title:
        h1 = soup.find("h1")
        title = _clean_text(h1.get_text(" ")) if h1 else url
    title = title[:120]

    description = extract_description(soup)
    topics = extract_topics(soup)
    body = _soup_text(soup)
    summary = description or body[:280]
    content = body[:2500]
    return Page(url=url, title=title or "Untitled", summary=summary, topics=topics, content=content)


def _build_scanned_text(pages: list[Page]) -> str:
    parts: list[str] = []
    for p in pages:
        parts.append(p.title)
        parts.extend(p.topics)
        parts.append(p.content)
    return "\n".join(part for part in parts if part)


async def _crawl(client: httpx.AsyncClient, start_url: str) -> ScanResult | None:
    """Directly crawl the site. Returns None if the homepage is unreachable."""
    home = await fetch(client, start_url)
    if home is None:
        return None
    final_url, home_html = home
    home_soup = BeautifulSoup(home_html, "html.parser")

    company_name = extract_company_name(home_soup, final_url)
    site_summary = extract_description(home_soup)

    links = discover_links(home_soup, final_url)[: MAX_PAGES - 1]
    sub_results = await asyncio.gather(*(fetch(client, link) for link in links))

    pages: list[Page] = [build_page(final_url, home_html)]
    pages[0].title = pages[0].title or company_name
    for res in sub_results:
        if res is None:
            continue
        page_url, page_html = res
        if any(p.url == page_url for p in pages):
            continue
        pages.append(build_page(page_url, page_html))

    return ScanResult(
        website_url=final_url,
        company_name=company_name,
        site_summary=site_summary,
        scanned_text=_build_scanned_text(pages),
        pages=pages,
    )


async def _search_pages(
    client: httpx.AsyncClient, domain: str, existing_urls: set[str]
) -> list[Page]:
    """Build knowledge pages from SearXNG results when crawling isn't enough.

    Best-effort fetches the top result pages for real content; otherwise uses the
    search snippet so we still capture real, externally-sourced information.
    """
    results = await search.search(f"{domain} company official", max_results=6)
    if not results:
        results = await search.search(domain, max_results=6)

    pages: list[Page] = []
    fetched = 0
    for r in results:
        if r.url in existing_urls or any(p.url == r.url for p in pages):
            continue
        page: Page | None = None
        if fetched < 3:
            res = await fetch(client, r.url)
            if res is not None:
                _, html = res
                page = build_page(r.url, html)
                fetched += 1
        if page is None:
            snippet = r.content or r.title
            page = Page(
                url=r.url,
                title=r.title or r.url,
                summary=snippet[:280],
                topics=[],
                content=snippet[:1200],
            )
        pages.append(page)
        if len(pages) >= MAX_PAGES:
            break
    return pages


def _is_thin(result: ScanResult | None) -> bool:
    if result is None:
        return True
    return len(result.scanned_text) < 400


async def scan_website(raw_url: str) -> ScanResult:
    start_url = normalize_url(raw_url)
    domain = registrable_domain(urlparse(start_url).netloc)
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}

    async with httpx.AsyncClient(
        follow_redirects=True,
        headers=headers,
        http2=False,
        event_hooks={"request": [_egress_guard]},
    ) as client:
        crawled = await _crawl(client, start_url)

        # Crawl succeeded with rich content — use it directly.
        if not _is_thin(crawled):
            assert crawled is not None
            return crawled

        # Otherwise, augment / replace with SearXNG results.
        existing_urls = {p.url for p in crawled.pages} if crawled else set()
        search_pages = await _search_pages(client, domain, existing_urls)

    if crawled is None and not search_pages:
        raise ScanError(
            f"Could not reach {start_url} and web search returned nothing. "
            "Check the URL is correct, or that SearXNG is running."
        )

    if crawled is not None:
        pages = crawled.pages + search_pages
        company_name = crawled.company_name
        site_summary = crawled.site_summary
        final_url = crawled.website_url
    else:
        pages = search_pages
        # Best-effort name from the first search result / domain.
        company_name = " ".join(
            w.capitalize() for w in re.split(r"[-_.]", domain.split(".")[0]) if w
        )
        site_summary = search_pages[0].summary if search_pages else ""
        final_url = start_url

    return ScanResult(
        website_url=final_url,
        company_name=company_name,
        site_summary=site_summary,
        scanned_text=_build_scanned_text(pages),
        pages=pages,
        used_search=bool(search_pages),
        crawl_failed=crawled is None,
    )
