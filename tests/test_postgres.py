from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import database, db
from app.models import Base


@pytest.mark.skipif(not os.getenv("NEXUS_TEST_POSTGRES_URL"), reason="PostgreSQL integration URL not configured")
def test_pgvector_similarity_query_round_trip(monkeypatch):
    engine = create_engine(os.environ["NEXUS_TEST_POSTGRES_URL"], pool_pre_ping=True)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
    test_sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(db, "SessionLocal", test_sessions)
    try:
        database.initialize_database()
        user = db.create_user("vector-test@example.com", "Vector Test", "not-a-real-password-hash")
        project = db.create_project(user["id"], "Vector search", "Does pgvector retrieve the nearest source chunk?")
        inserted = db.add_sources(user["id"], project["id"], [{
            "provider": "integration-test",
            "source_type": "research_paper",
            "title": "Vector fixture source",
            "url": "https://example.org/vector-fixture",
            "content": "A fixed test source is used to verify vector persistence and cosine ranking.",
            "description": "pgvector smoke test",
        }])
        assert inserted == 1
        source = db.list_sources(user["id"], project["id"])[0]
        vector = [0.0] * 1536
        vector[0] = 1.0
        assert db.save_source_chunks(user["id"], project["id"], source["id"], ["nearest neighbour evidence"], [vector]) == 1
        results = db.search_chunks(user["id"], project["id"], "nearest neighbour", vector, limit=3)
        assert results
        assert results[0]["source_id"] == source["id"]
        assert results[0]["score"] > 0.99
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
