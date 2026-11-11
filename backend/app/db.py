from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from .database import SessionLocal
from .models import ClaimEvidence, EvidenceClaim, Message, Project, Report, ResearchJob, ResearchSnapshot, Source, SourceChunk, User


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


# V3 evidence ledger and immutable research snapshots
def list_project_chunks(owner_id: int, project_id: int, limit: int = 600) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 2000))
    with SessionLocal() as session:
        rows = session.execute(
            select(SourceChunk, Source)
            .join(Source, Source.id == SourceChunk.source_id)
            .join(Project, Project.id == SourceChunk.project_id)
            .where(Project.owner_id == owner_id, SourceChunk.project_id == project_id)
            .order_by(Source.id.asc(), SourceChunk.chunk_index.asc())
            .limit(safe_limit)
        ).all()
        return [
            {"source_id": source.id, "chunk_index": chunk.chunk_index, "content": chunk.content,
             "title": source.title, "url": source.url, "provider": source.provider,
             "published_at": source.published_at, "source_type": source.source_type}
            for chunk, source in rows
        ]


def save_evidence_analysis(owner_id: int, project_id: int, items: list[dict[str, Any]], extraction_method: str) -> dict[str, int]:
    import hashlib
    import re
    created_claims = 0
    created_links = 0
    with SessionLocal() as session:
        project = session.scalar(select(Project).where(Project.id == project_id, Project.owner_id == owner_id))
        if not project:
            raise ValueError("Project not found.")
        for item in items[:60]:
            claim_text = re.sub(r"\s+", " ", str(item.get("text") or "")).strip()[:1800]
            if len(claim_text) < 24:
                continue
            normalized = re.sub(r"[^a-z0-9]+", " ", claim_text.lower()).strip()
            claim_key = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            claim = session.scalar(select(EvidenceClaim).where(
                EvidenceClaim.project_id == project_id, EvidenceClaim.claim_key == claim_key))
            if claim is None:
                claim = EvidenceClaim(project_id=project_id, text=claim_text, claim_key=claim_key,
                    assessment=str(item.get("assessment") or "needs_review"), extraction_method=extraction_method,
                    review_status="unreviewed")
                session.add(claim)
                session.flush()
                created_claims += 1
            else:
                claim.assessment = str(item.get("assessment") or "needs_review")
                claim.extraction_method = extraction_method
                claim.text = claim_text
            for evidence in item.get("evidence") or []:
                try:
                    source_id, chunk_index = int(evidence.get("source_id")), int(evidence.get("chunk_index"))
                except (TypeError, ValueError):
                    continue
                relation = str(evidence.get("relation") or "context")
                if relation not in {"supports", "contradicts", "context"}:
                    continue
                source = session.scalar(select(Source).where(Source.id == source_id, Source.project_id == project_id))
                chunk = session.scalar(select(SourceChunk).where(
                    SourceChunk.source_id == source_id, SourceChunk.project_id == project_id,
                    SourceChunk.chunk_index == chunk_index))
                if source is None or chunk is None:
                    continue
                excerpt = re.sub(r"\s+", " ", str(evidence.get("excerpt") or chunk.content)).strip()
                normalized_chunk = re.sub(r"\s+", " ", chunk.content).strip()
                if excerpt and excerpt[:900].lower() not in normalized_chunk.lower():
                    excerpt = normalized_chunk[:900]
                else:
                    excerpt = excerpt[:900]
                existing = session.scalar(select(ClaimEvidence).where(
                    ClaimEvidence.claim_id == claim.id, ClaimEvidence.source_id == source_id,
                    ClaimEvidence.chunk_index == chunk_index))
                if existing is None:
                    session.add(ClaimEvidence(claim_id=claim.id, source_id=source_id, chunk_index=chunk_index,
                        relation=relation, excerpt=excerpt or normalized_chunk[:900],
                        rationale=str(evidence.get("rationale") or "")[:800]))
                    created_links += 1
                else:
                    existing.relation = relation
                    existing.excerpt = excerpt or normalized_chunk[:900]
                    existing.rationale = str(evidence.get("rationale") or "")[:800]
        session.commit()
    return {"new_claims": created_claims, "new_evidence_links": created_links}


def list_evidence_claims(owner_id: int, project_id: int) -> dict[str, Any]:
    with SessionLocal() as session:
        claims = session.scalars(select(EvidenceClaim).join(Project, Project.id == EvidenceClaim.project_id)
            .where(Project.owner_id == owner_id, EvidenceClaim.project_id == project_id)
            .order_by(EvidenceClaim.created_at.desc(), EvidenceClaim.id.desc()).limit(250)).all()
        claim_ids = [claim.id for claim in claims]
        grouped: dict[int, list[dict[str, Any]]] = {claim_id: [] for claim_id in claim_ids}
        if claim_ids:
            rows = session.execute(select(ClaimEvidence, Source).join(Source, Source.id == ClaimEvidence.source_id)
                .join(EvidenceClaim, EvidenceClaim.id == ClaimEvidence.claim_id)
                .join(Project, Project.id == EvidenceClaim.project_id)
                .where(Project.owner_id == owner_id, EvidenceClaim.project_id == project_id,
                    ClaimEvidence.claim_id.in_(claim_ids), Source.project_id == project_id)
                .order_by(ClaimEvidence.id.asc())).all()
            for link, source in rows:
                grouped[link.claim_id].append({
                    "source_id": source.id, "source_title": source.title, "source_url": source.url,
                    "provider": source.provider, "published_at": source.published_at,
                    "chunk_index": link.chunk_index, "relation": link.relation,
                    "excerpt": link.excerpt, "rationale": link.rationale})
        items = [{
            "id": claim.id, "text": claim.text, "assessment": claim.assessment,
            "extraction_method": claim.extraction_method, "review_status": claim.review_status,
            "created_at": claim.created_at.isoformat() if claim.created_at else None,
            "updated_at": claim.updated_at.isoformat() if claim.updated_at else None,
            "evidence": grouped.get(claim.id, [])} for claim in claims]
        return {"claims": items, "summary": {
            "total": len(items), "reviewed": sum(1 for item in items if item["review_status"] != "unreviewed"),
            "contested": sum(1 for item in items if item["assessment"] == "contested"),
            "needs_review": sum(1 for item in items if item["review_status"] == "unreviewed")}}


def update_claim_review(owner_id: int, project_id: int, claim_id: int, review_status: str) -> dict[str, Any] | None:
    if review_status not in {"unreviewed", "confirmed", "rejected"}:
        raise ValueError("Review status must be unreviewed, confirmed, or rejected.")
    with SessionLocal() as session:
        claim = session.scalar(select(EvidenceClaim).join(Project, Project.id == EvidenceClaim.project_id).where(
            EvidenceClaim.id == claim_id, EvidenceClaim.project_id == project_id, Project.owner_id == owner_id))
        if claim is None:
            return None
        claim.review_status = review_status
        session.commit()
        session.refresh(claim)
        return {"id": claim.id, "text": claim.text, "assessment": claim.assessment,
            "extraction_method": claim.extraction_method, "review_status": claim.review_status}


def _snapshot_dict(row: ResearchSnapshot, include_manifest: bool = False) -> dict[str, Any]:
    item = {"id": row.id, "project_id": row.project_id, "digest": row.digest,
        "source_count": row.source_count, "chunk_count": row.chunk_count,
        "created_at": row.created_at.isoformat() if row.created_at else None}
    if include_manifest:
        item["manifest"] = row.manifest_json or {}
    return item


def create_project_snapshot(owner_id: int, project_id: int) -> dict[str, Any] | None:
    import hashlib
    import json
    with SessionLocal() as session:
        project = session.scalar(select(Project).where(Project.id == project_id, Project.owner_id == owner_id))
        if project is None:
            return None
        sources = session.scalars(select(Source).where(Source.project_id == project_id).order_by(Source.id.asc())).all()
        chunk_count = session.scalar(select(func.count(SourceChunk.id)).where(SourceChunk.project_id == project_id)) or 0
        created_at = datetime.now(timezone.utc).isoformat()
        source_manifest = []
        for source in sources:
            body = source.content or ""
            source_manifest.append({
                "source_id": source.id, "title": source.title, "url": source.url, "provider": source.provider,
                "source_type": source.source_type, "authors": source.authors, "published_at": source.published_at,
                "content_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                "content_characters": len(body), "metadata": source.metadata_json or {}})
        manifest = {"schema": "nexus-research-snapshot/v1", "created_at": created_at,
            "project": {"id": project.id, "title": project.title, "research_question": project.research_question,
                "description": project.description}, "source_count": len(source_manifest),
            "indexed_chunk_count": int(chunk_count), "sources": source_manifest,
            "integrity_note": "SHA-256 hashes cover stored source text and canonical manifest metadata; they do not prove an external publisher page will remain unchanged."}
        digest_payload = {key: value for key, value in manifest.items() if key != "created_at"}
        canonical = json.dumps(digest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        existing = session.scalar(select(ResearchSnapshot).where(
            ResearchSnapshot.project_id == project_id, ResearchSnapshot.digest == digest))
        if existing is not None:
            return _snapshot_dict(existing, include_manifest=True)
        row = ResearchSnapshot(project_id=project_id, digest=digest, source_count=len(source_manifest),
            chunk_count=int(chunk_count), manifest_json=manifest)
        session.add(row)
        session.commit()
        session.refresh(row)
        return _snapshot_dict(row, include_manifest=True)


def list_project_snapshots(owner_id: int, project_id: int) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        rows = session.scalars(select(ResearchSnapshot).join(Project, Project.id == ResearchSnapshot.project_id)
            .where(Project.owner_id == owner_id, ResearchSnapshot.project_id == project_id)
            .order_by(ResearchSnapshot.id.desc()).limit(100)).all()
        return [_snapshot_dict(row) for row in rows]


def get_project_snapshot(owner_id: int, project_id: int, snapshot_id: int) -> dict[str, Any] | None:
    with SessionLocal() as session:
        row = session.scalar(select(ResearchSnapshot).join(Project, Project.id == ResearchSnapshot.project_id).where(
            ResearchSnapshot.id == snapshot_id, ResearchSnapshot.project_id == project_id, Project.owner_id == owner_id))
        return _snapshot_dict(row, include_manifest=True) if row else None
