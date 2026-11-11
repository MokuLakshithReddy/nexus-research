from __future__ import annotations

import io
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from . import db
from .database import initialize_database
from .evidence import analyze_project_evidence
from .research.providers import PROVIDERS
from .security import (
    clear_session, enforce_same_origin, get_current_user, hash_password,
    require_csrf, set_session, verify_password,
)
from .services import (
    extract_url, grounded_answer, index_pending_sources, make_report,
    retrieve_relevant_chunks,
)

APP_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(APP_ROOT / ".env")
FRONTEND_DIR = APP_ROOT / "frontend"
DEFAULT_PROVIDERS = ["openalex", "crossref", "arxiv", "news", "web", "youtube", "x"]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if os.getenv("ENVIRONMENT", "development") == "production":
        from .security import SESSION_SECRET
        if SESSION_SECRET == "development-only-change-this-before-deploying":
            raise RuntimeError("SESSION_SECRET_KEY must be set in production.")
    initialize_database()
    yield


app = FastAPI(
    title="Nexus Research API",
    version="0.3.0",
    description="Multi-user research workspace with durable collection, evidence review, hybrid retrieval, and reproducible snapshots.",
    lifespan=lifespan,
)


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    full_name: str = Field(default="", max_length=120)
    password: str = Field(min_length=10, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=1, max_length=128)


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

class ClaimReviewRequest(BaseModel):
    review_status: str = Field(pattern="^(unreviewed|confirmed|rejected)$")


def ensure_project(user: dict[str, Any], project_id: int) -> dict[str, Any]:
    project = db.get_project(int(user["id"]), project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Research project not found.")
    return project


def connector_status() -> list[dict[str, Any]]:
    return [
        {"id": "openalex", "name": "OpenAlex", "kind": "Academic", "configured": True, "mode": "Public API",
         "detail": "Scholarly works, authors, abstracts where available, and citation counts."},
        {"id": "crossref", "name": "Crossref", "kind": "Academic", "configured": True, "mode": "Public API",
         "detail": "DOI metadata and publication records."},
        {"id": "arxiv", "name": "arXiv", "kind": "Academic", "configured": True, "mode": "Public API",
         "detail": "Preprints and abstracts."},
        {"id": "news", "name": "GDELT News", "kind": "News", "configured": True, "mode": "Public API",
         "detail": "Global news discovery; full text may require importing the publisher page."},
        {"id": "web", "name": "Brave Search", "kind": "Web", "configured": bool(os.getenv("BRAVE_SEARCH_API_KEY")),
         "mode": "API key required", "detail": "General web search."},
        {"id": "youtube", "name": "YouTube", "kind": "Video", "configured": bool(os.getenv("YOUTUBE_API_KEY")),
         "mode": "Official Data API", "detail": "Video discovery and metadata; transcript retrieval is not included."},
        {"id": "x", "name": "X", "kind": "Social", "configured": bool(os.getenv("X_BEARER_TOKEN")),
         "mode": "Official API", "detail": "Recent public posts; access depends on the API plan and token."},
        {"id": "instagram", "name": "Instagram", "kind": "Social", "configured": False,
         "mode": "Not connected", "detail": "Requires eligible Meta API access and permissions; no unrestricted scraping."},
        {"id": "facebook", "name": "Facebook", "kind": "Social", "configured": False,
         "mode": "Not connected", "detail": "Requires supported Meta Page access and app permissions."},
        {"id": "google_scholar", "name": "Google Scholar", "kind": "Academic", "configured": False,
         "mode": "Not directly integrated", "detail": "No official bulk API; OpenAlex, Crossref and arXiv are used for scholarly discovery."},
    ]


def _markdown_lines(markdown: str) -> list[tuple[str, str]]:
    output = []
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line:
            output.append(("space", ""))
        elif line.startswith("### "):
            output.append(("h3", line[4:]))
        elif line.startswith("## "):
            output.append(("h2", line[3:]))
        elif line.startswith("# "):
            output.append(("h1", line[2:]))
        elif line.startswith(("- ", "* ")):
            output.append(("bullet", line[2:]))
        else:
            output.append(("body", line))
    return output


def _docx_bytes(markdown: str) -> bytes:
    from docx import Document
    from docx.shared import Inches, Pt

    document = Document()
    section = document.sections[0]
    section.top_margin = Inches(0.7)
    section.bottom_margin = Inches(0.7)
    for kind, value in _markdown_lines(markdown):
        if kind == "space":
            continue
        if kind == "h1":
            document.add_heading(value, level=0)
        elif kind == "h2":
            document.add_heading(value, level=1)
        elif kind == "h3":
            document.add_heading(value, level=2)
        elif kind == "bullet":
            document.add_paragraph(value, style="List Bullet")
        else:
            paragraph = document.add_paragraph(value)
            paragraph.paragraph_format.space_after = Pt(6)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def _pdf_bytes(title: str, markdown: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm, title=title)
    base = getSampleStyleSheet()
    styles = {
        "h1": ParagraphStyle("NexusH1", parent=base["Title"], fontSize=21, leading=26,
                             textColor=colors.HexColor("#20251b"), alignment=TA_LEFT, spaceAfter=10),
        "h2": ParagraphStyle("NexusH2", parent=base["Heading2"], fontSize=14, leading=18,
                             textColor=colors.HexColor("#333d2c"), spaceBefore=12, spaceAfter=6),
        "h3": ParagraphStyle("NexusH3", parent=base["Heading3"], fontSize=11, leading=14, spaceBefore=8),
        "body": ParagraphStyle("NexusBody", parent=base["BodyText"], fontSize=9.2, leading=13,
                               textColor=colors.HexColor("#292d33"), spaceAfter=5),
        "bullet": ParagraphStyle("NexusBullet", parent=base["BodyText"], fontSize=9.2, leading=13,
                                 leftIndent=12, firstLineIndent=-8, spaceAfter=4),
    }
    story = []
    for kind, value in _markdown_lines(markdown):
        if kind == "space":
            story.append(Spacer(1, 3))
            continue
        escaped = xml_escape(value).replace("**", "")
        if kind == "bullet":
            story.append(Paragraph("• " + escaped, styles["bullet"]))
        else:
            story.append(Paragraph(escaped, styles.get(kind, styles["body"])))
    doc.build(story)
    return output.getvalue()


@app.get("/api/health")
def health():
    return {"ok": True, "name": "Nexus Research", "version": app.version}


@app.post("/api/auth/register", status_code=201)
def register(payload: RegisterRequest, request: Request, response: Response):
    enforce_same_origin(request)
    email = payload.email.lower().strip()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    try:
        user = db.create_user(email, payload.full_name, hash_password(payload.password))
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="An account with this email already exists.") from exc
    set_session(response, int(user["id"]))
    return {"user": user}


@app.post("/api/auth/login")
def login(payload: LoginRequest, request: Request, response: Response):
    enforce_same_origin(request)
    user, stored_hash = db.get_user_by_email(payload.email)
    if not user or not stored_hash or not verify_password(payload.password, stored_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="This account is unavailable.")
    set_session(response, int(user["id"]))
    return {"user": user}


@app.get("/api/auth/me")
def auth_me(user: dict[str, Any] = Depends(get_current_user)):
    return {"user": user}


@app.post("/api/auth/logout")
def logout(
    response: Response,
    user: dict[str, Any] = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
):
    clear_session(response)
    return {"ok": True}


@app.get("/api/connectors")
def get_connectors(user: dict[str, Any] = Depends(get_current_user)):
    return {"connectors": connector_status(), "ai_configured": bool(os.getenv("OPENAI_API_KEY")),
            "vector_search": bool(os.getenv("OPENAI_API_KEY"))}


@app.get("/api/projects")
def get_projects(user: dict[str, Any] = Depends(get_current_user)):
    return {"projects": db.list_projects(int(user["id"]))}


@app.post("/api/projects", status_code=201)
def create_project(
    payload: CreateProject,
    user: dict[str, Any] = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
):
    project = db.create_project(int(user["id"]), payload.title.strip(),
                                 payload.research_question.strip(), payload.description.strip())
    return {"project": project}


@app.get("/api/projects/{project_id}")
def project_detail(project_id: int, user: dict[str, Any] = Depends(get_current_user)):
    project = ensure_project(user, project_id)
    sources = db.list_sources(int(user["id"]), project_id)
    messages = db.list_messages(int(user["id"]), project_id)
    reports = db.list_reports(int(user["id"]), project_id)
    return {"project": project, "sources": sources, "messages": messages, "reports": reports}


@app.post("/api/projects/{project_id}/research", status_code=202)
def research_project(
    project_id: int,
    payload: StartResearch,
    user: dict[str, Any] = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
):
    project = ensure_project(user, project_id)
    query = (payload.query or project["research_question"]).strip()
    if len(query) < 4:
        raise HTTPException(status_code=422, detail="A research query of at least four characters is required.")
    providers = payload.providers or DEFAULT_PROVIDERS
    invalid = sorted(set(providers) - set(PROVIDERS))
    if invalid:
        raise HTTPException(status_code=422, detail=f"Unsupported provider(s): {', '.join(invalid)}")
    try:
        job = db.create_research_job(int(user["id"]), project_id, query, providers)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Research project not found.") from exc
    return {"job_id": job["id"], "status": job["status"], "message": "Research job queued. The worker will collect sources in the background."}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, user: dict[str, Any] = Depends(get_current_user)):
    job = db.get_research_job(int(user["id"]), job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Research job not found.")
    return {"job": job}


@app.post("/api/projects/{project_id}/sources/url", status_code=201)
async def import_url(
    project_id: int,
    payload: AddUrl,
    user: dict[str, Any] = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
):
    ensure_project(user, project_id)
    try:
        extracted = await extract_url(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not import this page: {str(exc)[:180]}") from exc
    owner_id = int(user["id"])
    source = {
        "provider": "manual_url", "source_type": "article", "title": extracted["title"],
        "url": extracted["url"], "description": extracted["description"], "content": extracted["content"],
        "relevance": 0.8, "metadata": {"import_method": "url"},
    }
    added = db.add_sources(owner_id, project_id, [source])
    stored = next((item for item in db.list_sources(owner_id, project_id) if item["url"] == extracted["url"]), None)
    if stored and added:
        from .services import index_source
        await index_source(owner_id, project_id, stored)
    return {"added": bool(added), "source": stored,
            "message": "Source imported and indexed." if added else "That URL is already in this workspace."}


@app.post("/api/projects/{project_id}/sources/upload", status_code=201)
async def upload_document(
    project_id: int,
    file: UploadFile = File(...),
    user: dict[str, Any] = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
):
    ensure_project(user, project_id)
    filename = Path(file.filename or "uploaded-document").name
    suffix = Path(filename).suffix.lower()
    if suffix not in {".txt", ".md", ".pdf", ".docx"}:
        raise HTTPException(status_code=415, detail="Supported formats: PDF, DOCX, TXT and Markdown.")
    raw = await file.read(15_000_001)
    if len(raw) > 15_000_000:
        raise HTTPException(status_code=413, detail="Document exceeds the 15 MB upload limit.")
    try:
        if suffix in {".txt", ".md"}:
            text = raw.decode("utf-8", errors="replace")
        elif suffix == ".pdf":
            from pypdf import PdfReader
            text = "\n\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(raw)).pages[:120])
        else:
            from docx import Document
            text = "\n".join(paragraph.text for paragraph in Document(io.BytesIO(raw)).paragraphs)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not read this document: {str(exc)[:160]}") from exc
    text = text.strip()
    if len(text) < 40:
        raise HTTPException(status_code=422, detail="No meaningful text could be extracted from this document.")
    source_url = f"upload://{project_id}/{re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)}"
    source = {
        "provider": "document_upload", "source_type": "document", "title": filename,
        "url": source_url, "description": text[:700], "content": text[:100000],
        "relevance": 0.9, "metadata": {"filename": filename, "content_type": file.content_type, "bytes": len(raw)},
    }
    owner_id = int(user["id"])
    added = db.add_sources(owner_id, project_id, [source])
    if added:
        stored = next((item for item in db.list_sources(owner_id, project_id) if item["url"] == source_url), None)
        if stored:
            from .services import index_source
            await index_source(owner_id, project_id, stored)
    return {"added": bool(added), "message": "Document imported and indexed in this workspace." if added else "That filename is already in this workspace."}




@app.get("/api/projects/{project_id}/evidence")
def get_evidence_ledger(
    project_id: int,
    user: dict[str, Any] = Depends(get_current_user),
):
    ensure_project(user, project_id)
    return db.list_evidence_claims(int(user["id"]), project_id)


@app.post("/api/projects/{project_id}/evidence/analyze")
async def analyze_evidence_ledger(
    project_id: int,
    user: dict[str, Any] = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
):
    ensure_project(user, project_id)
    try:
        return await analyze_project_evidence(int(user["id"]), project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Research project not found.") from exc


@app.patch("/api/projects/{project_id}/evidence/claims/{claim_id}/review")
def review_evidence_claim(
    project_id: int,
    claim_id: int,
    payload: ClaimReviewRequest,
    user: dict[str, Any] = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
):
    ensure_project(user, project_id)
    claim = db.update_claim_review(int(user["id"]), project_id, claim_id, payload.review_status)
    if claim is None:
        raise HTTPException(status_code=404, detail="Evidence claim not found.")
    return {"claim": claim}


@app.get("/api/projects/{project_id}/snapshots")
def list_research_snapshots(
    project_id: int,
    user: dict[str, Any] = Depends(get_current_user),
):
    ensure_project(user, project_id)
    return {"snapshots": db.list_project_snapshots(int(user["id"]), project_id)}


@app.post("/api/projects/{project_id}/snapshots", status_code=201)
def create_research_snapshot(
    project_id: int,
    user: dict[str, Any] = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
):
    ensure_project(user, project_id)
    snapshot = db.create_project_snapshot(int(user["id"]), project_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Research project not found.")
    return {"snapshot": snapshot}


@app.get("/api/projects/{project_id}/snapshots/{snapshot_id}")
def get_research_snapshot(
    project_id: int,
    snapshot_id: int,
    user: dict[str, Any] = Depends(get_current_user),
):
    ensure_project(user, project_id)
    snapshot = db.get_project_snapshot(int(user["id"]), project_id, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Research snapshot not found.")
    return {"snapshot": snapshot}


@app.post("/api/projects/{project_id}/chat")
async def chat(
    project_id: int,
    payload: ChatRequest,
    user: dict[str, Any] = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
):
    project = ensure_project(user, project_id)
    owner_id = int(user["id"])
    db.add_message(owner_id, project_id, "user", payload.message.strip())
    chunks = await retrieve_relevant_chunks(owner_id, project_id, payload.message.strip())
    answer, mode = await grounded_answer(payload.message.strip(), project, chunks)
    db.add_message(owner_id, project_id, "assistant", answer)
    return {"answer": answer, "mode": mode, "messages": db.list_messages(owner_id, project_id)}


@app.post("/api/projects/{project_id}/summarize")
async def summarize(
    project_id: int,
    user: dict[str, Any] = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
):
    project = ensure_project(user, project_id)
    owner_id = int(user["id"])
    chunks = await retrieve_relevant_chunks(owner_id, project_id, project["research_question"], limit=24)
    if not chunks:
        raise HTTPException(status_code=409, detail="Add research sources before requesting a summary.")
    answer, mode = await grounded_answer(
        "Summarize the key findings, repeated themes, contradictions, limitations and open questions.",
        project, chunks
    )
    return {"summary": answer, "mode": mode, "source_count": len({chunk["source_id"] for chunk in chunks})}


@app.post("/api/projects/{project_id}/reports", status_code=201)
async def generate_report(
    project_id: int,
    payload: ReportRequest,
    user: dict[str, Any] = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
):
    project = ensure_project(user, project_id)
    owner_id = int(user["id"])
    sources = db.list_sources(owner_id, project_id)
    chunks = await retrieve_relevant_chunks(owner_id, project_id, project["research_question"], limit=48)
    markdown, mode = await make_report(project, sources, chunks)
    title = (payload.title or f"Research report — {project['title']}").strip()
    report = db.add_report(owner_id, project_id, title, markdown)
    return {"report": report, "mode": mode}


@app.get("/api/reports/{report_id}/download")
def download_report(
    report_id: int,
    format: str = "md",
    user: dict[str, Any] = Depends(get_current_user),
):
    report = db.get_report(int(user["id"]), report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", report["title"]).strip("-").lower() or "research-report"
    if format == "md":
        return PlainTextResponse(
            report["markdown"], media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.md"'},
        )
    if format == "docx":
        content = _docx_bytes(report["markdown"])
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = f"{safe_name}.docx"
    elif format == "pdf":
        content = _pdf_bytes(report["title"], report["markdown"])
        media_type = "application/pdf"
        filename = f"{safe_name}.pdf"
    else:
        raise HTTPException(status_code=422, detail="Choose md, docx, or pdf.")
    return Response(content, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/", response_class=HTMLResponse)
def home():
    index = FRONTEND_DIR / "index.html"
    if not index.exists():
        return HTMLResponse("Nexus Research frontend missing.", status_code=500)
    return HTMLResponse(index.read_text(encoding="utf-8"))


app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="assets")
