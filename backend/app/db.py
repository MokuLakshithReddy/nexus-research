from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

DATA_DIR = Path(os.getenv("NEXUS_DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
DB_PATH = Path(os.getenv("NEXUS_DB_PATH", DATA_DIR / "nexus.db"))


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def transaction():
    conn = connect()
    try:
        conn.execute("BEGIN")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                research_question TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'ready',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                provider TEXT NOT NULL,
                source_type TEXT NOT NULL DEFAULT 'article',
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                authors TEXT DEFAULT '',
                published_at TEXT DEFAULT '',
                description TEXT DEFAULT '',
                content TEXT DEFAULT '',
                relevance REAL DEFAULT 0,
                metadata TEXT DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_id, url)
            );
            CREATE INDEX IF NOT EXISTS idx_sources_project ON sources(project_id, created_at DESC);
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                markdown TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS research_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                query TEXT NOT NULL,
                status TEXT NOT NULL,
                providers_json TEXT NOT NULL DEFAULT '{}',
                added_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def create_project(title: str, question: str, description: str = "") -> dict[str, Any]:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO projects(title, research_question, description) VALUES (?, ?, ?)",
            (title, question, description),
        )
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)


def get_project(project_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return row_to_dict(row)


def list_projects() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT p.*,
                      (SELECT COUNT(*) FROM sources s WHERE s.project_id = p.id) AS source_count,
                      (SELECT COUNT(*) FROM reports r WHERE r.project_id = p.id) AS report_count
               FROM projects p ORDER BY p.updated_at DESC, p.id DESC"""
        ).fetchall()
        return [dict(row) for row in rows]


def add_sources(project_id: int, sources: list[dict[str, Any]]) -> int:
    inserted = 0
    with connect() as conn:
        for source in sources:
            metadata = source.get("metadata", "{}")
            if not isinstance(metadata, str):
                metadata = json.dumps(metadata, ensure_ascii=False)
            cursor = conn.execute(
                """INSERT OR IGNORE INTO sources
                   (project_id, provider, source_type, title, url, authors, published_at,
                    description, content, relevance, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    project_id,
                    source.get("provider", "manual"),
                    source.get("source_type", "article"),
                    source.get("title") or "Untitled source",
                    source["url"],
                    source.get("authors", ""),
                    source.get("published_at", ""),
                    source.get("description", ""),
                    source.get("content", ""),
                    float(source.get("relevance", 0) or 0),
                    metadata,
                ),
            )
            inserted += cursor.rowcount
        conn.execute("UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (project_id,))
    return inserted


def list_sources(project_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM sources WHERE project_id = ? ORDER BY relevance DESC, created_at DESC",
            (project_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_source(source_id: int, project_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM sources WHERE id = ? AND project_id = ?", (source_id, project_id)
        ).fetchone()
        return row_to_dict(row)


def add_message(project_id: int, role: str, content: str) -> dict[str, Any]:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO messages(project_id, role, content) VALUES (?, ?, ?)",
            (project_id, role, content),
        )
        row = conn.execute("SELECT * FROM messages WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)


def list_messages(project_id: int, limit: int = 60) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE project_id = ? ORDER BY id DESC LIMIT ?",
            (project_id, limit),
        ).fetchall()
        return [dict(row) for row in reversed(rows)]


def add_report(project_id: int, title: str, markdown: str) -> dict[str, Any]:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO reports(project_id, title, markdown) VALUES (?, ?, ?)",
            (project_id, title, markdown),
        )
        row = conn.execute("SELECT * FROM reports WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)


def list_reports(project_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, project_id, title, created_at FROM reports WHERE project_id = ? ORDER BY id DESC",
            (project_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_report(report_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        return row_to_dict(conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone())


def add_research_run(project_id: int, query: str, status: str, providers: dict[str, Any], added_count: int) -> None:
    import json
    with connect() as conn:
        conn.execute(
            "INSERT INTO research_runs(project_id, query, status, providers_json, added_count) VALUES (?, ?, ?, ?, ?)",
            (project_id, query, status, json.dumps(providers), added_count),
        )
