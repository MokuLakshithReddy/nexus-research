from __future__ import annotations

import ipaddress
import os
import re
import socket
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import httpx


class ArticleTextParser(HTMLParser):
    SKIP_TAGS = {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
        if tag == "title":
            self.in_title = True
        if tag in {"p", "article", "main", "h1", "h2", "h3", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        if tag == "title":
            self.in_title = False
        if tag in {"p", "article", "main", "h1", "h2", "h3", "li"}:
            self.parts.append("\n")

    def handle_data(self, data):
        text = " ".join(data.split())
        if not text:
            return
        if self.in_title:
            self.title_parts.append(text)
        if not self.skip_depth:
            self.parts.append(text)


def validate_public_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only absolute HTTP or HTTPS URLs are supported.")
    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost", "localhost.localdomain"} or host.endswith((".local", ".internal")):
        raise ValueError("Local and internal network addresses cannot be imported.")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise ValueError("The source hostname could not be resolved.") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError("Private, local, or reserved network addresses cannot be imported.")
    return url.strip()


async def extract_url(url: str) -> dict[str, Any]:
    safe_url = validate_public_url(url)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; NexusResearch/0.1; +https://github.com/)"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(14.0, connect=6.0), follow_redirects=False, headers=headers) as client:
        response = await client.get(safe_url)
        if response.status_code in {301, 302, 303, 307, 308}:
            raise ValueError("This URL redirects. Open the final destination and import that URL instead.")
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" not in content_type and "text/plain" not in content_type:
            raise ValueError("This URL is not an HTML or plain-text page. Upload the document instead.")
        if len(response.content) > 5_000_000:
            raise ValueError("The page is larger than the 5 MB import limit.")
        text = response.text
    parser = ArticleTextParser()
    parser.feed(text[:2_000_000])
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(parser.parts)).strip()
    if len(body) < 80:
        raise ValueError("Not enough readable text was found on this page.")
    title = " ".join(parser.title_parts).strip() or urlparse(safe_url).netloc
    return {"title": title[:300], "content": body[:50000], "description": body[:500], "url": safe_url}


def simple_summary(sources: list[dict[str, Any]], max_sentences: int = 12) -> str:
    candidates: list[tuple[float, str, int]] = []
    for source in sources:
        text = (source.get("content") or source.get("description") or "").strip()
        if not text:
            continue
        sentences = re.split(r"(?<=[.!?])\s+", text)
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 45:
                continue
            # Lightweight extractive ranking: favor informative sentence length and source prominence.
            score = min(len(sentence), 260) / 260 + float(source.get("relevance") or 0) * 0.35
            candidates.append((score, sentence, int(source["id"])))
    candidates.sort(reverse=True, key=lambda x: x[0])
    chosen: list[str] = []
    seen: set[str] = set()
    for _, sentence, source_id in candidates:
        normalized = re.sub(r"\W+", " ", sentence.lower()).strip()
        if normalized in seen:
            continue
        seen.add(normalized)
        chosen.append(f"{sentence} [Source {source_id}]")
        if len(chosen) >= max_sentences:
            break
    if not chosen:
        return "There is not enough extracted source text to summarize yet. Add article URLs or upload research documents."
    return "\n\n".join(f"- {line}" for line in chosen)


def relevant_sources(sources: list[dict[str, Any]], question: str, limit: int = 8) -> list[dict[str, Any]]:
    terms = {w.lower() for w in re.findall(r"[a-zA-Z0-9]{3,}", question)}
    scored = []
    for source in sources:
        corpus = f"{source.get('title', '')} {source.get('description', '')} {source.get('content', '')}".lower()
        overlap = sum(1 for term in terms if term in corpus)
        scored.append((overlap + float(source.get("relevance") or 0), source))
    return [item for _, item in sorted(scored, key=lambda x: x[0], reverse=True)[:limit]]


async def llm_text(system_prompt: str, user_prompt: str) -> str | None:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    payload = {"model": model, "temperature": 0.2,
               "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]}
    async with httpx.AsyncClient(timeout=httpx.Timeout(65.0, connect=8.0)) as client:
        response = await client.post("https://api.openai.com/v1/chat/completions", json=payload,
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        response.raise_for_status()
        data = response.json()
    return data["choices"][0]["message"]["content"].strip()


async def grounded_answer(question: str, project: dict[str, Any], sources: list[dict[str, Any]]) -> tuple[str, str]:
    picked = relevant_sources(sources, question)
    context = "\n\n".join(
        f"[Source {s['id']}] {s['title']}\nURL: {s['url']}\nPublished: {s.get('published_at') or 'unknown'}\n"
        f"{(s.get('content') or s.get('description') or '')[:5000]}" for s in picked
    )
    if not picked:
        return ("I don't have source material to answer that yet. Run research or add source URLs first.", "no_sources")
    system = (
        "You are Nexus, a careful research assistant. Answer only from the supplied source context. "
        "Cite factual claims using [Source N]. Do not invent references or unsupported facts. "
        "State when evidence is insufficient, distinguish source statements from your synthesis, "
        "and flag disagreement between sources. Keep the answer useful and structured."
    )
    prompt = f"Research question: {project['research_question']}\nUser question: {question}\n\nSOURCE CONTEXT:\n{context}"
    try:
        answer = await llm_text(system, prompt)
    except Exception as exc:
        answer = None
        error_note = f"AI provider unavailable ({str(exc)[:120]}). "
    else:
        error_note = ""
    if answer:
        return answer, "openai"
    summary = simple_summary(picked, max_sentences=6)
    return (f"{error_note}I’m using a local extractive fallback because OPENAI_API_KEY is not configured. "
            "This is a starting-point digest, not a full reasoning model response.\n\n" + summary, "extractive_fallback")


async def make_report(project: dict[str, Any], sources: list[dict[str, Any]]) -> tuple[str, str]:
    bibliography = "\n".join(
        f"[{s['id']}] {s['title']}. {s.get('authors') or 'Author not listed'}. "
        f"{s.get('published_at') or 'Date not listed'}. {s['url']}"
        for s in sources
    )
    context = "\n\n".join(
        f"[Source {s['id']}] {s['title']} ({s.get('published_at') or 'date unknown'})\n"
        f"{s['url']}\n{(s.get('content') or s.get('description') or '')[:3500]}"
        for s in sources[:24]
    )
    system = (
        "Write a rigorous research report using only the supplied evidence. Structure it with title, "
        "executive summary, research question and scope, methodology/limitations, thematic findings, "
        "cross-source synthesis, disagreements and evidence gaps, conclusion, and numbered references. "
        "Cite claims inline as [Source N]. Never make up sources, quotations, sample sizes, or statistics. "
        "Label weak or indirect evidence and separate observed source facts from interpretation."
    )
    prompt = f"Topic: {project['title']}\nResearch question: {project['research_question']}\n\nSOURCES:\n{context}\n\nREFERENCE LIST:\n{bibliography}"
    try:
        report = await llm_text(system, prompt)
    except Exception:
        report = None
    if report:
        return report, "openai"
    if not sources:
        return ("# Research draft\n\nNo sources have been collected yet. Run a research search or import documents, then regenerate this report.", "empty")
    extract = simple_summary(sources, max_sentences=14)
    report = (
        f"# {project['title']}\n\n## Research question\n{project['research_question']}\n\n"
        "## Evidence snapshot\n\nThis is an automatically assembled draft. It uses extractive excerpts and has not been synthesized by an LLM. Review each source and verify claims before publication.\n\n"
        f"## Key excerpts\n\n{extract}\n\n## Limitations\n\nThe current draft reflects only the sources stored in this workspace. Search coverage depends on enabled providers and their API access. No claim should be treated as conclusive without reviewing its cited source.\n\n"
        f"## References\n\n{bibliography}"
    )
    return report, "extractive_fallback"
