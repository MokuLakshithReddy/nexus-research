from __future__ import annotations

import asyncio
import html
import os
import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote_plus

import httpx

TIMEOUT = httpx.Timeout(18.0, connect=8.0)
USER_AGENT = "NexusResearch/0.1 (research workspace; contact: configure NEXUS_CONTACT_EMAIL)"


def _abstract_from_inverted_index(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    tokens: list[tuple[int, str]] = []
    for word, positions in index.items():
        for pos in positions:
            tokens.append((pos, word))
    return " ".join(word for _, word in sorted(tokens))


def _author_names(items: list[dict[str, Any]] | None) -> str:
    return ", ".join(
        (item.get("author", {}).get("display_name") or item.get("family") or item.get("name") or "")
        for item in (items or [])
        if item.get("author", {}).get("display_name") or item.get("family") or item.get("name")
    )


async def openalex_search(query: str, limit: int = 8) -> list[dict[str, Any]]:
    params = {"search": query, "per-page": min(limit, 20), "select": "id,doi,title,publication_year,publication_date,authorships,abstract_inverted_index,cited_by_count,primary_location"}
    email = os.getenv("NEXUS_CONTACT_EMAIL")
    if email:
        params["mailto"] = email
    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
        response = await client.get("https://api.openalex.org/works", params=params)
        response.raise_for_status()
        payload = response.json()
    results = []
    for item in payload.get("results", []):
        title = item.get("title") or "Untitled paper"
        doi = item.get("doi")
        location = (item.get("primary_location") or {}).get("landing_page_url")
        url = doi or location or item.get("id")
        if not url:
            continue
        abstract = _abstract_from_inverted_index(item.get("abstract_inverted_index"))
        authors = ", ".join(
            a.get("author", {}).get("display_name", "")
            for a in (item.get("authorships") or [])[:8]
            if a.get("author", {}).get("display_name")
        )
        results.append({
            "provider": "openalex", "source_type": "research_paper", "title": title,
            "url": url, "authors": authors, "published_at": item.get("publication_date") or str(item.get("publication_year") or ""),
            "description": abstract[:1600], "content": abstract[:16000],
            "relevance": min(float(item.get("cited_by_count") or 0) / 1000, 1.0),
            "metadata": {"doi": item.get("doi"), "cited_by_count": item.get("cited_by_count", 0)},
        })
    return results


async def crossref_search(query: str, limit: int = 6) -> list[dict[str, Any]]:
    params = {"query": query, "rows": min(limit, 20), "select": "DOI,title,author,published,created,URL,type,container-title,abstract"}
    email = os.getenv("NEXUS_CONTACT_EMAIL")
    if email:
        params["mailto"] = email
    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
        response = await client.get("https://api.crossref.org/works", params=params)
        response.raise_for_status()
        items = response.json().get("message", {}).get("items", [])
    results = []
    for item in items:
        doi = item.get("DOI")
        title = (item.get("title") or ["Untitled work"])[0]
        if not doi:
            continue
        date_parts = (item.get("published") or {}).get("date-parts", [[""]])[0]
        results.append({
            "provider": "crossref", "source_type": "research_paper", "title": title,
            "url": f"https://doi.org/{doi}", "authors": _author_names(item.get("author")),
            "published_at": "-".join(map(str, date_parts)),
            "description": re.sub(r"<[^>]+>", " ", item.get("abstract", ""))[:1600],
            "content": re.sub(r"<[^>]+>", " ", item.get("abstract", ""))[:16000],
            "relevance": 0.45, "metadata": {"doi": doi, "type": item.get("type"), "journal": (item.get("container-title") or [""])[0]},
        })
    return results


async def arxiv_search(query: str, limit: int = 6) -> list[dict[str, Any]]:
    params = {"search_query": f"all:{query}", "start": 0, "max_results": min(limit, 15), "sortBy": "relevance"}
    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
        response = await client.get("https://export.arxiv.org/api/query", params=params)
        response.raise_for_status()
        xml_text = response.text
    root = ET.fromstring(xml_text)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    results = []
    for entry in root.findall("a:entry", ns):
        title = " ".join((entry.findtext("a:title", default="", namespaces=ns)).split())
        summary = " ".join((entry.findtext("a:summary", default="", namespaces=ns)).split())
        link = entry.find("a:id", ns)
        if not link is None and link.text:
            results.append({
                "provider": "arxiv", "source_type": "research_paper", "title": title or "Untitled preprint",
                "url": link.text.strip(), "authors": ", ".join(a.findtext("a:name", default="", namespaces=ns) for a in entry.findall("a:author", ns)[:8]),
                "published_at": entry.findtext("a:published", default="", namespaces=ns)[:10],
                "description": summary[:1600], "content": summary[:16000], "relevance": 0.5,
                "metadata": {"category": [c.attrib.get("term") for c in entry.findall("a:category", ns)]},
            })
    return results


async def gdelt_search(query: str, limit: int = 8) -> list[dict[str, Any]]:
    params = {"query": query, "mode": "ArtList", "format": "json", "maxrecords": min(limit, 20), "sort": "HybridRel"}
    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
        response = await client.get("https://api.gdeltproject.org/api/v2/doc/doc", params=params)
        response.raise_for_status()
        payload = response.json()
    return [
        {
            "provider": "gdelt", "source_type": "news", "title": item.get("title") or "Untitled article",
            "url": item.get("url"), "authors": item.get("source", ""), "published_at": item.get("seendate", ""),
            "description": f"News result from {item.get('domain', 'publisher')} · {item.get('language', 'unknown language')}",
            "content": "", "relevance": 0.55,
            "metadata": {"domain": item.get("domain"), "language": item.get("language"), "source_country": item.get("sourcecountry")},
        }
        for item in payload.get("articles", []) if item.get("url")
    ]


async def brave_search(query: str, limit: int = 8) -> list[dict[str, Any]]:
    key = os.getenv("BRAVE_SEARCH_API_KEY")
    if not key:
        return []
    params = {"q": query, "count": min(limit, 20), "safesearch": "moderate"}
    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"X-Subscription-Token": key, "Accept": "application/json"}) as client:
        response = await client.get("https://api.search.brave.com/res/v1/web/search", params=params)
        response.raise_for_status()
        payload = response.json()
    items = (payload.get("web") or {}).get("results", [])
    return [
        {"provider": "brave_search", "source_type": "article", "title": x.get("title") or "Web result",
         "url": x.get("url"), "authors": x.get("profile", {}).get("long_name", ""),
         "published_at": x.get("page_age", ""), "description": x.get("description", ""),
         "content": x.get("description", ""), "relevance": 0.65, "metadata": {"extra_snippets": x.get("extra_snippets", [])}}
        for x in items if x.get("url")
    ]


async def youtube_search(query: str, limit: int = 6) -> list[dict[str, Any]]:
    key = os.getenv("YOUTUBE_API_KEY")
    if not key:
        return []
    params = {"part": "snippet", "type": "video", "maxResults": min(limit, 10), "q": query, "key": key}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get("https://www.googleapis.com/youtube/v3/search", params=params)
        response.raise_for_status()
        payload = response.json()
    results = []
    for item in payload.get("items", []):
        video_id = (item.get("id") or {}).get("videoId")
        snippet = item.get("snippet") or {}
        if video_id:
            results.append({"provider": "youtube", "source_type": "video", "title": snippet.get("title", "YouTube video"),
                            "url": f"https://www.youtube.com/watch?v={video_id}", "authors": snippet.get("channelTitle", ""),
                            "published_at": snippet.get("publishedAt", "")[:10], "description": snippet.get("description", "")[:1600],
                            "content": snippet.get("description", "")[:8000], "relevance": 0.55,
                            "metadata": {"channel_id": snippet.get("channelId"), "video_id": video_id}})
    return results


async def x_search(query: str, limit: int = 6) -> list[dict[str, Any]]:
    token = os.getenv("X_BEARER_TOKEN")
    if not token:
        return []
    params = {"query": f"({query}) -is:retweet lang:en", "max_results": min(max(limit, 10), 100), "tweet.fields": "created_at,public_metrics,lang"}
    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"Authorization": f"Bearer {token}"}) as client:
        response = await client.get("https://api.x.com/2/tweets/search/recent", params=params)
        response.raise_for_status()
        payload = response.json()
    return [
        {"provider": "x", "source_type": "social_post", "title": (t.get("text", "")[:110] + "…") if len(t.get("text", "")) > 110 else t.get("text", "X post"),
         "url": f"https://x.com/i/web/status/{t['id']}", "authors": "X user", "published_at": t.get("created_at", "")[:10],
         "description": t.get("text", ""), "content": t.get("text", ""), "relevance": 0.5, "metadata": {"public_metrics": t.get("public_metrics", {})}}
        for t in payload.get("data", []) if t.get("id")
    ]


PROVIDERS = {
    "openalex": openalex_search,
    "crossref": crossref_search,
    "arxiv": arxiv_search,
    "news": gdelt_search,
    "web": brave_search,
    "youtube": youtube_search,
    "x": x_search,
}


async def run_research(query: str, enabled: list[str] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    chosen = enabled or ["openalex", "crossref", "arxiv", "news", "web", "youtube", "x"]
    tasks = {name: PROVIDERS[name](query) for name in chosen if name in PROVIDERS}
    outcomes = await asyncio.gather(*tasks.values(), return_exceptions=True)
    collected: list[dict[str, Any]] = []
    statuses: dict[str, Any] = {}
    for (name, _), outcome in zip(tasks.items(), outcomes):
        if isinstance(outcome, Exception):
            statuses[name] = {"status": "error", "message": str(outcome)[:240]}
            continue
        statuses[name] = {"status": "connected" if outcome else "no_results_or_not_configured", "count": len(outcome)}
        collected.extend(outcome)
    # Stable URL-based deduplication; preserve the richer first record.
    seen: set[str] = set()
    unique = []
    for item in collected:
        url = (item.get("url") or "").strip().rstrip("/")
        if not url or url in seen:
            continue
        seen.add(url)
        item["url"] = url
        unique.append(item)
    return unique, statuses
