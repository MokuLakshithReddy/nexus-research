from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import db, database
from app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'nexus-v2-test.db').as_posix()}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    testing_sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(db, "SessionLocal", testing_sessions)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with TestClient(app) as test_client:
        yield test_client
    engine.dispose()


def register(client: TestClient, email: str = "researcher@example.com") -> dict:
    response = client.post("/api/auth/register", json={
        "email": email,
        "full_name": "Researcher",
        "password": "nexus-test-password-2026",
    })
    assert response.status_code == 201, response.text
    return response.json()["user"]


def csrf_headers(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("nexus_csrf")
    assert token
    return {"X-CSRF-Token": token}
