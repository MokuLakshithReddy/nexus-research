from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from .database import SessionLocal
from .models import Message, Project, Report, ResearchJob, Source, SourceChunk, User


def _user_dict(row: User | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {"id": row.id, "email": row.email, "full_name": row.full_name, "is_active": row.is_active,
            "created_at": row.created_at.isoformat() if row.created_at else None}


def _project_dict(row: Project) -> dict[str, Any]:
    return {"id": row.id, "owner_id": row.owner_id, "title": row.title,
            "research_question": row.research_question, "description": row.description,
            "status": row.status, "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None}


def _source_dict(row: Source) -> dict[str, Any]:
    return {"id": row.id, "project_id": row.project_id, "provider": row.provider,
            "source_type": row.source_type, "title": row.title, "url": row.url,
            "authors": row.authors, "published_at": row.published_at,
            "description": row.description, "content": row.content,
            "relevance": row.relevance, "metadata": row.metadata_json or {},
            "created_at": row.created_at.isoformat() if row.created_at else None}


def _message_dict(row: Message) -> dict[str, Any]:
    return {"id": row.id, "project_id": row.project_id, "role": row.role,
            "content": row.content, "created_at": row.created_at.isoformat() if row.created_at else None}


def _report_dict(row: Report, include_markdown: bool = True) -> dict[str, Any]:
    data = {"id": row.id, "project_id": row.project_id, "title": row.title,
            "created_at": row.created_at.isoformat() if row.created_at else None}
    if include_markdown:
        data["markdown"] = row.markdown
    return data


def _job_dict(row: ResearchJob) -> dict[str, Any]:
    return {"id": row.id, "project_id": row.project_id, "query": row.query,
            "providers": row.providers or [], "status": row.status, "attempts": row.attempts,
            "discovered_count": row.discovered_count, "added_count": row.added_count,
            "provider_status": row.provider_status or {}, "error_message": row.error_message,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None}


# Authentication persistence

def create_user(email: str, full_name: str, password_hash: str) -> dict[str, Any]:
    with SessionLocal() as session:
        user = User(email=email.lower().strip(), full_name=full_name.strip(), password_hash=password_hash)
        session.add(user)
        session.commit()
        session.refresh(user)
        return _user_dict(user)


def get_user_by_email(email: str) -> tuple[dict[str, Any] | None, str | None]:
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == email.lower().strip()))
        return _user_dict(user), user.password_hash if user else None


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    with SessionLocal() as session:
        return _user_dict(session.get(User, user_id))


# All workspace reads and writes are scoped by owner_id supplied by the authenticated session.

def create_project(owner_id: int, title: str, question: str, description: str = "") -> dict[str, Any]:
    with SessionLocal() as session:
        project = Project(owner_id=owner_id, title=title, research_question=question, description=description)
        session.add(project)
        session.commit()
        session.refresh(project)
        return _project_dict(project)


def get_project(owner_id: int, project_id: int) -> dict[str, Any] | None:
    with SessionLocal() as session:
        row = session.scalar(select(Project).where(Project.id == project_id, Project.owner_id == owner_id))
        return _project_dict(row) if row else None


def list_projects(owner_id: int) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        rows = session.scalars(
            select(Project).where(Project.owner_id == owner_id).order_by(Project.updated_at.desc(), Project.id.desc())
        ).all()
        projects = []
        for row in rows:
            projects.append({
                **_project_dict(row),
                "source_count": session.scalar(select(func.count(Source.id)).where(Source.project_id == row.id)) or 0,
                "report_count": session.scalar(select(func.count(Report.id)).where(Report.project_id == row.id)) or 0,
            })
        return projects


def add_sources(owner_id: int, project_id: int, sources: list[dict[str, Any]]) -> int:
    inserted = 0
    with SessionLocal() as session:
        project = session.scalar(select(Project).where(Project.id == project_id, Project.owner_id == owner_id))
        if not project:
            return 0
        for item in sources:
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            exists = session.scalar(select(Source.id).where(Source.project_id == project_id, Source.url == url))
            if exists:
                continue
            session.add(Source(
                project_id=project_id,
                provider=str(item.get("provider") or "manual")[:64],
                source_type=str(item.get("source_type") or "article")[:48],
                title=str(item.get("title") or "Untitled source")[:500],
                url=url[:2048],
                authors=str(item.get("authors") or ""),
                published_at=str(item.get("published_at") or "")[:80],
                description=str(item.get("description") or ""),
                content=str(item.get("content") or ""),
                relevance=float(item.get("relevance") or 0),
                metadata_json=item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
            ))
            inserted += 1
        project.updated_at = datetime.now(timezone.utc)
        session.commit()
    return inserted


def list_sources(owner_id: int, project_id: int) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        rows = session.scalars(
            select(Source).join(Project, Project.id == Source.project_id)
            .where(Source.project_id == project_id, Project.owner_id == owner_id)
            .order_by(Source.relevance.desc(), Source.created_at.desc())
        ).all()
        return [_source_dict(row) for row in rows]


def get_source(owner_id: int, project_id: int, source_id: int) -> dict[str, Any] | None:
    with SessionLocal() as session:
        row = session.scalar(
            select(Source).join(Project, Project.id == Source.project_id)
            .where(Source.id == source_id, Source.project_id == project_id, Project.owner_id == owner_id)
        )
        return _source_dict(row) if row else None


def add_message(owner_id: int, project_id: int, role: str, content: str) -> dict[str, Any]:
    with SessionLocal() as session:
        project = session.scalar(select(Project).where(Project.id == project_id, Project.owner_id == owner_id))
        if not project:
            raise ValueError("Project not found.")
        row = Message(project_id=project_id, role=role, content=content)
        session.add(row)
        session.commit()
        session.refresh(row)
        return _message_dict(row)


def list_messages(owner_id: int, project_id: int, limit: int = 80) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        rows = session.scalars(
            select(Message).join(Project, Project.id == Message.project_id)
            .where(Message.project_id == project_id, Project.owner_id == owner_id)
            .order_by(Message.id.desc()).limit(limit)
        ).all()
        return [_message_dict(row) for row in reversed(rows)]


def add_report(owner_id: int, project_id: int, title: str, markdown: str) -> dict[str, Any]:
    with SessionLocal() as session:
        project = session.scalar(select(Project).where(Project.id == project_id, Project.owner_id == owner_id))
        if not project:
            raise ValueError("Project not found.")
        row = Report(project_id=project_id, title=title, markdown=markdown)
        session.add(row)
        session.commit()
        session.refresh(row)
        return _report_dict(row)


def list_reports(owner_id: int, project_id: int) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        rows = session.scalars(
            select(Report).join(Project, Project.id == Report.project_id)
            .where(Report.project_id == project_id, Project.owner_id == owner_id)
            .order_by(Report.id.desc())
        ).all()
        return [_report_dict(row, include_markdown=False) for row in rows]


def get_report(owner_id: int, report_id: int) -> dict[str, Any] | None:
    with SessionLocal() as session:
        row = session.scalar(
            select(Report).join(Project, Project.id == Report.project_id)
            .where(Report.id == report_id, Project.owner_id == owner_id)
        )
        return _report_dict(row) if row else None


# Durable, database-backed research queue

def create_research_job(owner_id: int, project_id: int, query: str, providers: list[str]) -> dict[str, Any]:
    with SessionLocal() as session:
        project = session.scalar(select(Project).where(Project.id == project_id, Project.owner_id == owner_id))
        if not project:
            raise ValueError("Project not found.")
        job = ResearchJob(id=str(uuid4()), owner_id=owner_id, project_id=project_id,
                          query=query, providers=providers)
        session.add(job)
        project.status = "research_queued"
        session.commit()
        session.refresh(job)
        return _job_dict(job)


def get_research_job(owner_id: int, job_id: str) -> dict[str, Any] | None:
    with SessionLocal() as session:
        job = session.scalar(select(ResearchJob).where(
            ResearchJob.id == job_id, ResearchJob.owner_id == owner_id
        ))
        return _job_dict(job) if job else None


def claim_next_job() -> dict[str, Any] | None:
    with SessionLocal() as session:
        job = session.scalar(
            select(ResearchJob)
            .where(ResearchJob.status == "queued", ResearchJob.attempts < 3)
            .order_by(ResearchJob.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if not job:
            return None
        job.status = "running"
        job.attempts += 1
        job.started_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(job)
        return _job_dict(job)


def finish_research_job(job_id: str, discovered_count: int, added_count: int,
                        provider_status: dict[str, Any]) -> None:
    with SessionLocal() as session:
        job = session.get(ResearchJob, job_id)
        if not job:
            return
        job.status = "completed"
        job.discovered_count = discovered_count
        job.added_count = added_count
        job.provider_status = provider_status
        job.error_message = ""
        job.finished_at = datetime.now(timezone.utc)
        project = session.get(Project, job.project_id)
        if project:
            project.status = "ready"
        session.commit()


def fail_research_job(job_id: str, message: str, retry: bool = True) -> None:
    with SessionLocal() as session:
        job = session.get(ResearchJob, job_id)
        if not job:
            return
        job.error_message = message[:1200]
        job.status = "queued" if retry and job.attempts < 3 else "failed"
        if job.status == "failed":
            job.finished_at = datetime.now(timezone.utc)
            project = session.get(Project, job.project_id)
            if project:
                project.status = "research_failed"
        session.commit()


def recover_stale_jobs(stale_after_minutes: int = 15) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=stale_after_minutes)
    recovered = 0
    with SessionLocal() as session:
        rows = session.scalars(
            select(ResearchJob).where(
                ResearchJob.status == "running", ResearchJob.started_at < cutoff
            )
        ).all()
        for job in rows:
            job.status = "queued" if job.attempts < 3 else "failed"
            job.error_message = "Worker lease expired; job was recovered automatically."
            if job.status == "failed":
                job.finished_at = datetime.now(timezone.utc)
                project = session.get(Project, job.project_id)
                if project:
                    project.status = "research_failed"
            recovered += 1
        session.commit()
    return recovered


def list_unindexed_sources(owner_id: int, project_id: int) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        rows = session.scalars(
            select(Source).join(Project, Project.id == Source.project_id)
            .outerjoin(SourceChunk, SourceChunk.source_id == Source.id)
            .where(Project.owner_id == owner_id, Source.project_id == project_id, SourceChunk.id.is_(None))
            .distinct()
        ).all()
        return [_source_dict(row) for row in rows]


def save_source_chunks(owner_id: int, project_id: int, source_id: int,
                       chunks: list[str], embeddings: list[list[float] | None]) -> int:
    with SessionLocal() as session:
        source = session.scalar(
            select(Source).join(Project, Project.id == Source.project_id)
            .where(Source.id == source_id, Source.project_id == project_id, Project.owner_id == owner_id)
        )
        if not source:
            return 0
        session.query(SourceChunk).filter(SourceChunk.source_id == source_id).delete()
        rows = [
            SourceChunk(project_id=project_id, source_id=source_id, chunk_index=index,
                        content=chunk, embedding=embeddings[index] if index < len(embeddings) else None)
            for index, chunk in enumerate(chunks)
        ]
        session.add_all(rows)
        session.commit()
        return len(rows)


def search_chunks(owner_id: int, project_id: int, query: str,
                  query_embedding: list[float] | None = None, limit: int = 12) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        base = (
            select(SourceChunk, Source)
            .join(Source, Source.id == SourceChunk.source_id)
            .join(Project, Project.id == SourceChunk.project_id)
            .where(Project.owner_id == owner_id, SourceChunk.project_id == project_id)
        )
        if query_embedding and session.bind and session.bind.dialect.name == "postgresql":
            distance = SourceChunk.embedding.cosine_distance(query_embedding)
            rows = session.execute(
                select(SourceChunk, Source, distance.label("distance"))
                .join(Source, Source.id == SourceChunk.source_id)
                .join(Project, Project.id == SourceChunk.project_id)
                .where(Project.owner_id == owner_id, SourceChunk.project_id == project_id,
                       SourceChunk.embedding.is_not(None))
                .order_by(distance.asc()).limit(limit)
            ).all()
            return [
                {"source_id": chunk.source_id, "chunk_index": chunk.chunk_index, "content": chunk.content,
                 "title": source.title, "url": source.url, "published_at": source.published_at,
                 "source_type": source.source_type, "score": max(0.0, 1.0 - float(distance_value))}
                for chunk, source, distance_value in rows
            ]

        # Bounded lexical fallback for SQLite development and missing embeddings.
        import re
        terms = {word.lower() for word in re.findall(r"[a-zA-Z0-9]{3,}", query)}
        rows = session.execute(base.order_by(SourceChunk.id.desc()).limit(1500)).all()
        ranked = []
        for chunk, source in rows:
            body = f"{source.title} {source.description} {chunk.content}".lower()
            overlap = sum(1 for term in terms if term in body)
            if overlap or not terms:
                ranked.append((overlap, chunk, source))
        ranked.sort(key=lambda item: (item[0], item[1].id), reverse=True)
        return [
            {"source_id": chunk.source_id, "chunk_index": chunk.chunk_index, "content": chunk.content,
             "title": source.title, "url": source.url, "published_at": source.published_at,
             "source_type": source.source_type, "score": float(score)}
            for score, chunk, source in ranked[:limit]
        ]
