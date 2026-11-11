from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse
from dotenv import load_dotenv
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db
from .research.providers import run_research
from .services import extract_url, grounded_answer, make_report

APP_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(APP_ROOT / ".env")
FRONTEND_DIR = APP_ROOT / "frontend"

@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    yield


app = FastAPI(
    title="Nexus Research API",
    version="0.1.0",
    description="Source-grounded research workspace and multi-provider collection API.",
    lifespan=lifespan,
)


class CreateProject(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    research_question: str = Field(min_length=8, max_length=1200)
    description: str = Field(default="", max_length=2000)


class StartResearch(BaseModel):
    query: str | None = Field(default=None, max_length=1200)
    providers: list[str] | None = None


class AddUrl(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=4000)


class ReportRequest(BaseModel):
    title: str | None = Field(default=None, max_length=180)


def ensure_project(project_id: int) -> dict[str, Any]:
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Research project not found.")
    return project


def serialize_source(source: dict[str, Any]) -> dict[str, Any]:
    item = dict(source)
    try:
        item["metadata"] = json.loads(item.get("metadata") or "{}")
    except (TypeError, json.JSONDecodeError):
        item["metadata"] = {}
    return item


def connector_status() -> list[dict[str, Any]]:
    return [
        {"id": "openalex", "name": "OpenAlex", "kind": "Academic", "configured": True, "mode": "Public API", "detail": "Scholarly works, authors, abstracts where available, and citation counts."},
        {"id": "crossref", "name": "Crossref", "kind": "Academic", "configured": True, "mode": "Public API", "detail": "DOI metadata and publication records."},
        {"id": "arxiv", "name": "arXiv", "kind": "Academic", "configured": True, "mode": "Public API", "detail": "Preprints and abstracts."},
        {"id": "news", "name": "GDELT News", "kind": "News", "configured": True, "mode": "Public API", "detail": "Global news article discovery. Full article content may require importing the publisher URL."},
        {"id": "web", "name": "Brave Search", "kind": "Web", "configured": bool(os.getenv("BRAVE_SEARCH_API_KEY")), "mode": "API key required", "detail": "General web search. Add BRAVE_SEARCH_API_KEY to enable."},
        {"id": "youtube", "name": "YouTube", "kind": "Video", "configured": bool(os.getenv("YOUTUBE_API_KEY")), "mode": "Official Data API", "detail": "Video discovery and metadata. Transcript extraction is not included in this version."},
        {"id": "x", "name": "X", "kind": "Social", "configured": bool(os.getenv("X_BEARER_TOKEN")), "mode": "Official API", "detail": "Recent public posts; access depends on your X API plan and token."},
        {"id": "instagram", "name": "Instagram", "kind": "Social", "configured": False, "mode": "Not connected", "detail": "Requires eligible Meta API access and permissions; no unrestricted scraping."},
        {"id": "facebook", "name": "Facebook", "kind": "Social", "configured": False, "mode": "Not connected", "detail": "Requires eligible Meta app permissions and supported Page/content access."},
        {"id": "google_scholar", "name": "Google Scholar", "kind": "Academic", "configured": False, "mode": "Not directly integrated", "detail": "No official bulk API. Use OpenAlex, Crossref, and arXiv for structured academic discovery."},
    ]


@app.get("/api/health")
def health():
    return {"ok": True, "name": "Nexus Research", "version": app.version}


@app.get("/api/connectors")
def get_connectors():
    return {"connectors": connector_status(), "ai_configured": bool(os.getenv("OPENAI_API_KEY"))}


@app.get("/api/projects")
def get_projects():
    return {"projects": db.list_projects()}


@app.post("/api/projects", status_code=201)
def create_project(payload: CreateProject):
    project = db.create_project(payload.title.strip(), payload.research_question.strip(), payload.description.strip())
    return {"project": project}


@app.get("/api/projects/{project_id}")
def project_detail(project_id: int):
    project = ensure_project(project_id)
    sources = [serialize_source(x) for x in db.list_sources(project_id)]
    messages = db.list_messages(project_id)
    reports = db.list_reports(project_id)
    return {"project": project, "sources": sources, "messages": messages, "reports": reports}


@app.post("/api/projects/{project_id}/research")
async def research_project(project_id: int, payload: StartResearch):
    project = ensure_project(project_id)
    query = (payload.query or project["research_question"]).strip()
    if len(query) < 4:
        raise HTTPException(status_code=422, detail="A research query of at least four characters is required.")
    sources, provider_status = await run_research(query, payload.providers)
    added = db.add_sources(project_id, sources)
    db.add_research_run(project_id, query, "completed", provider_status, added)
    detail = {"provider_status": provider_status, "discovered": len(sources), "added": added,
              "message": f"Found {len(sources)} results and added {added} new sources to this workspace."}
    return detail


@app.post("/api/projects/{project_id}/sources/url", status_code=201)
async def import_url(project_id: int, payload: AddUrl):
    ensure_project(project_id)
    try:
        extracted = await extract_url(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not import this page: {str(exc)[:180]}") from exc
    source = {
        "provider": "manual_url", "source_type": "article", "title": extracted["title"],
        "url": extracted["url"], "description": extracted["description"], "content": extracted["content"],
        "relevance": 0.8, "metadata": json.dumps({"import_method": "url"}),
    }
    added = db.add_sources(project_id, [source])
    all_sources = db.list_sources(project_id)
    created = next((s for s in all_sources if s["url"] == extracted["url"]), None)
    return {"added": bool(added), "source": serialize_source(created) if created else None,
            "message": "Source imported." if added else "That URL is already in this workspace."}


@app.post("/api/projects/{project_id}/sources/upload", status_code=201)
async def upload_document(project_id: int, file: UploadFile = File(...)):
    ensure_project(project_id)
    filename = file.filename or "uploaded-document"
    suffix = Path(filename).suffix.lower()
    allowed = {".txt", ".md", ".pdf", ".docx"}
    if suffix not in allowed:
        raise HTTPException(status_code=415, detail="Supported formats: PDF, DOCX, TXT and Markdown.")
    raw = await file.read()
    if len(raw) > 15_000_000:
        raise HTTPException(status_code=413, detail="Document exceeds the 15 MB upload limit.")
    text = ""
    try:
        if suffix in {".txt", ".md"}:
            text = raw.decode("utf-8", errors="replace")
        elif suffix == ".pdf":
            from pypdf import PdfReader
            import io
            reader = PdfReader(io.BytesIO(raw))
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages[:120])
        elif suffix == ".docx":
            from docx import Document
            import io
            document = Document(io.BytesIO(raw))
            text = "\n".join(p.text for p in document.paragraphs)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not read this document: {str(exc)[:160]}") from exc
    text = text.strip()
    if len(text) < 40:
        raise HTTPException(status_code=422, detail="No meaningful text could be extracted from this document.")
    pseudo_url = f"upload://{project_id}/{filename.replace(' ', '_')}"
    source = {
        "provider": "document_upload", "source_type": "document", "title": filename,
        "url": pseudo_url, "description": text[:700], "content": text[:100000], "relevance": 0.9,
        "metadata": json.dumps({"filename": filename, "content_type": file.content_type, "bytes": len(raw)}),
    }
    added = db.add_sources(project_id, [source])
    return {"added": bool(added), "message": "Document imported and indexed in this workspace."}


@app.post("/api/projects/{project_id}/chat")
async def chat(project_id: int, payload: ChatRequest):
    project = ensure_project(project_id)
    db.add_message(project_id, "user", payload.message.strip())
    sources = db.list_sources(project_id)
    answer, mode = await grounded_answer(payload.message.strip(), project, sources)
    db.add_message(project_id, "assistant", answer)
    return {"answer": answer, "mode": mode, "messages": db.list_messages(project_id)}


@app.post("/api/projects/{project_id}/summarize")
async def summarize(project_id: int):
    project = ensure_project(project_id)
    sources = db.list_sources(project_id)
    if not sources:
        raise HTTPException(status_code=409, detail="Add research sources before requesting a summary.")
    answer, mode = await grounded_answer("Summarize the research findings, identify repeated themes and note conflicting or missing evidence.", project, sources)
    return {"summary": answer, "mode": mode, "source_count": len(sources)}


@app.post("/api/projects/{project_id}/reports", status_code=201)
async def generate_report(project_id: int, payload: ReportRequest):
    project = ensure_project(project_id)
    sources = db.list_sources(project_id)
    markdown, mode = await make_report(project, sources)
    title = (payload.title or f"Research report — {project['title']}").strip()
    report = db.add_report(project_id, title, markdown)
    return {"report": report, "mode": mode}


@app.get("/api/reports/{report_id}/download")
def download_report(report_id: int):
    report = db.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    filename = re_safe_filename(report["title"]) + ".md"
    return PlainTextResponse(
        report["markdown"],
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def re_safe_filename(value: str) -> str:
    import re
    name = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower()
    return (name or "research-report")[:80]


@app.get("/", response_class=HTMLResponse)
def home():
    index = FRONTEND_DIR / "index.html"
    if not index.exists():
        return HTMLResponse("Nexus Research frontend missing.", status_code=500)
    return HTMLResponse(index.read_text(encoding="utf-8"))


app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="assets")
