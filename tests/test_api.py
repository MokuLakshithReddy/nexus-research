from __future__ import annotations

from fastapi.testclient import TestClient

from app import db
from app.main import app
from conftest import csrf_headers, register


def create_project(client: TestClient) -> int:
    response = client.post(
        "/api/projects",
        headers=csrf_headers(client),
        json={
            "title": "AI and employment research",
            "research_question": "How is generative AI affecting employment patterns in India?",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["project"]["id"]


def test_health_is_public_but_workspace_requires_auth(client):
    assert client.get("/api/health").json()["ok"] is True
    assert client.get("/api/projects").status_code == 401
    assert client.get("/api/connectors").status_code == 401


def test_account_registration_and_logout(client):
    user = register(client)
    assert user["email"] == "researcher@example.com"
    assert client.get("/api/auth/me").json()["user"]["id"] == user["id"]
    logout = client.post("/api/auth/logout", headers=csrf_headers(client), json={})
    assert logout.status_code == 200
    assert client.get("/api/projects").status_code == 401


def test_project_isolation_between_accounts(client):
    register(client, "owner@example.com")
    project_id = create_project(client)

    other = TestClient(app)
    try:
        register(other, "different@example.com")
        assert other.get("/api/projects").json()["projects"] == []
        assert other.get(f"/api/projects/{project_id}").status_code == 404
        assert other.get("/api/reports/999").status_code == 404
    finally:
        other.close()


def test_research_jobs_are_durable_and_owner_scoped(client):
    user = register(client)
    project_id = create_project(client)
    response = client.post(
        f"/api/projects/{project_id}/research",
        headers=csrf_headers(client),
        json={"query": "generative AI employment", "providers": ["openalex", "arxiv"]},
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    status_response = client.get(f"/api/jobs/{job_id}")
    assert status_response.status_code == 200
    assert status_response.json()["job"]["status"] == "queued"

    claimed = db.claim_next_job()
    assert claimed and claimed["id"] == job_id
    db.finish_research_job(job_id, 4, 3, {"openalex": {"status": "connected", "count": 4}})
    finished = client.get(f"/api/jobs/{job_id}").json()["job"]
    assert finished["status"] == "completed"
    assert finished["discovered_count"] == 4
    assert finished["added_count"] == 3


def test_upload_chat_summary_and_exports(client):
    register(client)
    project_id = create_project(client)
    payload = (
        b"This report examines generative artificial intelligence and the labor market. "
        b"The authors find that task exposure differs substantially across occupations. "
        b"The study also warns that exposure does not directly imply job displacement."
    )
    upload = client.post(
        f"/api/projects/{project_id}/sources/upload",
        headers=csrf_headers(client),
        files={"file": ("employment-study.txt", payload, "text/plain")},
    )
    assert upload.status_code == 201, upload.text
    detail = client.get(f"/api/projects/{project_id}").json()
    assert len(detail["sources"]) == 1

    chat = client.post(
        f"/api/projects/{project_id}/chat",
        headers=csrf_headers(client),
        json={"message": "What does the uploaded study say about task exposure?"},
    )
    assert chat.status_code == 200
    assert "Source 1" in chat.json()["answer"]

    summary = client.post(f"/api/projects/{project_id}/summarize", headers=csrf_headers(client), json={})
    assert summary.status_code == 200
    assert summary.json()["source_count"] == 1

    generated = client.post(f"/api/projects/{project_id}/reports", headers=csrf_headers(client), json={})
    assert generated.status_code == 201
    report_id = generated.json()["report"]["id"]

    markdown = client.get(f"/api/reports/{report_id}/download?format=md")
    docx = client.get(f"/api/reports/{report_id}/download?format=docx")
    pdf = client.get(f"/api/reports/{report_id}/download?format=pdf")
    assert markdown.status_code == docx.status_code == pdf.status_code == 200
    assert "References" in markdown.text
    assert docx.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert pdf.headers["content-type"] == "application/pdf"


def test_frontend_and_static_assets_are_served(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "Nexus Research" in page.text
    assert "auth-screen" in page.text
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/assets/styles.css").status_code == 200


def test_unknown_job_does_not_leak_data(client):
    register(client)
    assert client.get("/api/jobs/not-a-real-job").status_code == 404
