from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import db
from app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test-nexus.db")
    with TestClient(app) as test_client:
        yield test_client


def test_health_and_connectors(client):
    assert client.get("/api/health").json()["ok"] is True
    connectors = client.get("/api/connectors").json()["connectors"]
    connector_ids = {item["id"] for item in connectors}
    assert {"openalex", "crossref", "arxiv", "news", "youtube", "x"}.issubset(connector_ids)


def test_project_create_and_detail(client):
    created = client.post("/api/projects", json={
        "title": "AI in Indian employment",
        "research_question": "How is generative AI affecting employment in India?",
    })
    assert created.status_code == 201
    project_id = created.json()["project"]["id"]
    detail = client.get(f"/api/projects/{project_id}")
    assert detail.status_code == 200
    assert detail.json()["project"]["title"] == "AI in Indian employment"
    assert detail.json()["sources"] == []


def test_unknown_project_is_404(client):
    response = client.get("/api/projects/999999")
    assert response.status_code == 404


def test_source_metadata_is_json_serialized(client):
    created = client.post("/api/projects", json={
        "title": "Research persistence",
        "research_question": "How should source metadata be stored safely?",
    }).json()["project"]
    inserted = db.add_sources(created["id"], [{
        "provider": "test", "source_type": "article", "title": "Example source",
        "url": "https://example.org/paper", "metadata": {"topic": "testing", "rank": 2},
    }])
    assert inserted == 1
    detail = client.get(f"/api/projects/{created['id']}").json()
    assert detail["sources"][0]["title"] == "Example source"
    assert detail["sources"][0]["metadata"]["topic"] == "testing"


def test_research_chat_summary_and_report_flow(client, monkeypatch):
    async def fake_research(query, enabled=None):
        return ([{
            "provider": "test_provider",
            "source_type": "research_paper",
            "title": "An example evidence paper",
            "url": "https://example.org/research-paper",
            "authors": "A. Researcher",
            "published_at": "2025-01-01",
            "description": "The study reports a measurable change in the selected outcome.",
            "content": "The study reports a measurable change in the selected outcome across the sampled group. The authors also describe limits in the available data.",
            "relevance": 0.8,
            "metadata": {"fixture": True},
        }], {"test_provider": {"status": "connected", "count": 1}})

    monkeypatch.setattr("app.main.run_research", fake_research)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    project = client.post("/api/projects", json={
        "title": "Evidence flow test",
        "research_question": "What does this test study report about the selected outcome?",
    }).json()["project"]
    project_id = project["id"]

    research = client.post(f"/api/projects/{project_id}/research", json={})
    assert research.status_code == 200
    assert research.json()["added"] == 1

    chat = client.post(f"/api/projects/{project_id}/chat", json={"message": "What did the study find?"})
    assert chat.status_code == 200
    assert "Source 1" in chat.json()["answer"]

    summary = client.post(f"/api/projects/{project_id}/summarize")
    assert summary.status_code == 200
    assert summary.json()["source_count"] == 1

    report = client.post(f"/api/projects/{project_id}/reports", json={})
    assert report.status_code == 201
    report_id = report.json()["report"]["id"]
    download = client.get(f"/api/reports/{report_id}/download")
    assert download.status_code == 200
    assert "References" in download.text


def test_frontend_and_assets_are_served(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "Nexus Research" in page.text
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/assets/styles.css").status_code == 200


def test_text_document_upload_is_indexed(client):
    project = client.post("/api/projects", json={
        "title": "Document import test",
        "research_question": "What is contained in this uploaded document?",
    }).json()["project"]
    text = b"This document contains a substantial amount of useful research text for the test. It includes evidence, scope and a concise conclusion for extraction."
    response = client.post(
        f"/api/projects/{project['id']}/sources/upload",
        files={"file": ("field-notes.txt", text, "text/plain")},
    )
    assert response.status_code == 201
    detail = client.get(f"/api/projects/{project['id']}").json()
    assert len(detail["sources"]) == 1
    assert detail["sources"][0]["title"] == "field-notes.txt"
