from __future__ import annotations

from fastapi.testclient import TestClient

from app.evidence import extractive_candidates, parse_model_claims
from app.main import app
from conftest import csrf_headers, register


def _project(client: TestClient) -> int:
    response = client.post(
        "/api/projects",
        headers=csrf_headers(client),
        json={
            "title": "Evidence ledger test",
            "research_question": "What does the evidence say about task exposure?",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["project"]["id"]


def _upload(client: TestClient, project_id: int) -> None:
    text = (
        "The study reports that exposure to generative artificial intelligence varies across occupations. "
        "Researchers distinguish task exposure from direct job displacement because the same technology can "
        "automate some tasks while complementing other activities. The authors describe substantial uncertainty "
        "because the available observations do not establish long term employment effects."
    ).encode()
    response = client.post(
        f"/api/projects/{project_id}/sources/upload",
        headers=csrf_headers(client),
        files={"file": ("evidence-notes.txt", text, "text/plain")},
    )
    assert response.status_code == 201, response.text


def test_extractive_candidates_are_context_not_verification():
    chunks = [{
        "source_id": 5,
        "chunk_index": 0,
        "content": "The study reports that exposure to generative artificial intelligence varies substantially across occupations.",
    }]
    candidates = extractive_candidates(chunks)
    assert candidates
    assert candidates[0]["assessment"] == "needs_review"
    assert candidates[0]["evidence"][0]["relation"] == "context"


def test_model_parser_rejects_unknown_sources_and_non_verbatim_quotes():
    chunks = [{
        "source_id": 5,
        "chunk_index": 0,
        "content": "The study reports that exposure varies substantially across occupations and industries.",
    }]
    payload = (
        '[{"claim":"Exposure varies substantially across occupations and industries in the study.",'
        '"evidence":[{"source_id":5,"chunk_index":0,"relation":"supports",'
        '"quote":"exposure varies substantially across occupations and industries"}]},'
        '{"claim":"A separate unsupported claim with enough length to pass validation.",'
        '"evidence":[{"source_id":999,"chunk_index":0,"relation":"supports",'
        '"quote":"This quote is not in the stored source passage at all."}]}]'
    )
    parsed = parse_model_claims(payload, chunks)
    assert len(parsed) == 1
    assert parsed[0]["assessment"] == "support_indicated"
    assert parsed[0]["evidence"][0]["source_id"] == 5


def test_evidence_analysis_creates_traceable_candidates_and_review_state(client):
    register(client)
    project_id = _project(client)
    _upload(client, project_id)

    analysis = client.post(
        f"/api/projects/{project_id}/evidence/analyze",
        headers=csrf_headers(client),
        json={},
    )
    assert analysis.status_code == 200, analysis.text
    assert analysis.json()["claims"] >= 1
    assert analysis.json()["method"] == "extractive"

    ledger = client.get(f"/api/projects/{project_id}/evidence")
    assert ledger.status_code == 200
    claims = ledger.json()["claims"]
    assert claims
    assert claims[0]["review_status"] == "unreviewed"
    assert claims[0]["evidence"]
    assert claims[0]["evidence"][0]["relation"] == "context"
    assert claims[0]["evidence"][0]["source_url"].startswith("upload://")

    claim_id = claims[0]["id"]
    reviewed = client.patch(
        f"/api/projects/{project_id}/evidence/claims/{claim_id}/review",
        headers=csrf_headers(client),
        json={"review_status": "confirmed"},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["claim"]["review_status"] == "confirmed"

    ledger_after = client.get(f"/api/projects/{project_id}/evidence").json()
    assert next(item for item in ledger_after["claims"] if item["id"] == claim_id)["review_status"] == "confirmed"


def test_research_snapshot_is_stable_and_owner_scoped(client):
    register(client, "snapshot-owner@example.com")
    project_id = _project(client)
    _upload(client, project_id)

    created = client.post(
        f"/api/projects/{project_id}/snapshots",
        headers=csrf_headers(client),
        json={},
    )
    assert created.status_code == 201, created.text
    snapshot = created.json()["snapshot"]
    assert len(snapshot["digest"]) == 64
    assert snapshot["manifest"]["schema"] == "nexus-research-snapshot/v1"
    assert snapshot["source_count"] == 1

    fetched = client.get(f"/api/projects/{project_id}/snapshots/{snapshot['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["snapshot"]["digest"] == snapshot["digest"]

    other = TestClient(app)
    try:
        register(other, "snapshot-other@example.com")
        assert other.get(f"/api/projects/{project_id}/snapshots").status_code == 404
        assert other.get(f"/api/projects/{project_id}/evidence").status_code == 404
    finally:
        other.close()
