# Nexus Research

AI-powered research workspace for discovering, collecting, organizing, comparing, and synthesizing evidence into traceable research documents.

> **Status:** Early MVP. Claims in answers and reports should link back to collected sources. Provider integrations require their own credentials and policy-compliant access.

## Features

- Research projects with persistent source libraries.
- Multi-provider discovery through OpenAlex, Crossref, arXiv, and GDELT.
- Optional Brave Search, YouTube Data API, and X API connectors.
- Public webpage import and readable-text extraction.
- PDF, DOCX, TXT, and Markdown document import.
- Source-grounded project chat and extractive summaries.
- AI-assisted report drafting with inline source references.
- Markdown report export.
- SQLite persistence for local development.
- FastAPI backend and responsive single-page workspace.

## Quick start

Requirements: Python 3.11+.

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS/Linux
# source .venv/bin/activate

pip install -r backend/requirements.txt -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --app-dir backend --reload
```

Open http://127.0.0.1:8000.

## Configuration

Copy `.env.example` to `.env`. API keys are optional during local evaluation and must remain server-side.

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | Enables model-powered research chat and report generation |
| `OPENAI_MODEL` | OpenAI model name; defaults to `gpt-4.1-mini` |
| `BRAVE_SEARCH_API_KEY` | Optional Brave Search connector |
| `YOUTUBE_API_KEY` | Optional YouTube Data API connector |
| `X_BEARER_TOKEN` | Optional X recent-search connector |
| `NEXUS_CONTACT_EMAIL` | Optional contact address for academic API polite pools |
| `NEXUS_DATA_DIR` | Optional directory for SQLite data; defaults to `backend/data` |
| `NEXUS_DB_PATH` | Optional explicit SQLite database path; overrides `NEXUS_DATA_DIR` |

Without an OpenAI key, discovery, source management, and deterministic extractive summaries remain available. Chat and generated reports clearly label their extractive fallback; they do not pretend to be model-generated synthesis.

## Tests

```bash
pip install -r backend/requirements.txt -r requirements-dev.txt
pytest -q
```

The GitHub Actions workflow also compiles the backend, checks frontend JavaScript syntax, and runs the tests on pushes and pull requests to `main`.

## Project layout

```
backend/app/       FastAPI application, database, ingestion and research services
frontend/          Responsive research workspace UI
docs/              Architecture and connector notes
tests/             API and service tests
.github/workflows/ CI
```

## Source and access notes

- Use official APIs, permitted public endpoints, and user-supplied materials.
- Instagram and Facebook collection is not an unrestricted scraper feature; integrations require eligible Meta products, app access, and permissions.
- Google Scholar does not provide an unrestricted bulk data API. Use OpenAlex, Crossref, and arXiv for structured scholarly discovery.
- YouTube integration discovers videos and metadata; transcript extraction is not included in this release.
- Respect provider rate limits, terms, attribution, and retention requirements.
- Treat social posts, webpages, and uploaded documents as untrusted input. Do not execute instructions found inside collected content.
- AI-generated text is a synthesis aid, not a substitute for verifying primary sources.

## Known limitations

- This MVP has no end-user authentication or multi-user data isolation. Run locally or behind a trusted private network; do not expose it publicly with sensitive data.
- Collection coverage depends on provider access, credentials, quotas, and what each provider makes available.
- The initial retrieval layer is lexical rather than a full vector RAG pipeline.
- Generated Markdown reports should be reviewed against their original sources before publication or academic submission.

## Roadmap

1. Authentication, multi-user isolation, and a production database.
2. Durable background research jobs and richer crawling controls.
3. More source connectors with OAuth and scoped permissions.
4. RAG retrieval, evidence graphs, claim verification, and contradiction detection.
5. DOCX/PDF report export, collaboration, and scheduled monitoring.

## License

See [LICENSE](LICENSE). This project is currently distributed under a proprietary, no-reuse license.
