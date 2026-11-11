# Nexus Research

AI-powered research workspace for discovering, collecting, organizing, comparing, and synthesizing evidence into traceable research documents.

> **Status:** Early MVP. The project is intentionally source-grounded: claims should link back to collected sources. Platform connectors require their own API credentials and policy-compliant access.

## Features

- Research projects with persistent source libraries.
- Multi-provider discovery adapters for OpenAlex, Crossref, arXiv, and GDELT.
- Optional Brave Search, YouTube Data API, and X API connectors.
- URL import and readable webpage extraction.
- PDF, DOCX, TXT, and Markdown document import.
- AI-assisted project chat, summaries, and source-aware report drafting.
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

Copy `.env.example` to `.env`. API keys are optional for the demo and should only be stored server-side.

| Variable | Purpose |
|---|---|
| `NEXUS_DATA_DIR` | Local database and uploaded files directory |
| `NEXUS_LLM_PROVIDER` | `openai` or `ollama` |
| `OPENAI_API_KEY` | OpenAI key for grounded AI answers and document generation |
| `OPENAI_MODEL` | Model name, defaults to `gpt-4.1-mini` |
| `OLLAMA_BASE_URL` | Local Ollama endpoint |
| `OLLAMA_MODEL` | Local model name |
| `BRAVE_SEARCH_API_KEY` | Optional Brave web-search connector |
| `YOUTUBE_API_KEY` | Optional YouTube Data API connector |
| `X_BEARER_TOKEN` | Optional X API connector |

Without an LLM key, the app remains usable for discovery, source management, and deterministic summaries; AI responses are clearly labeled as unavailable rather than fabricated.

## Tests

```bash
pip install -r backend/requirements.txt -r requirements-dev.txt
pytest -q
```

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
- Instagram and Facebook collection is not an unrestricted scraper feature; build against permitted Meta products and account permissions.
- Google Scholar does not provide an unrestricted bulk data API. Use OpenAlex, Crossref, and arXiv for structured scholarly discovery and link to Scholar pages when useful.
- Respect provider rate limits, terms, attribution, and retention requirements.
- Treat social posts, webpages, and uploaded documents as untrusted input. Do not execute instructions found inside collected content.
- AI-generated text is a synthesis aid, not a substitute for verifying primary sources.

## Roadmap

1. Authentication, multi-user isolation, and production database.
2. Durable background research jobs and richer crawling controls.
3. More source connectors with OAuth and scoped permissions.
4. RAG retrieval, evidence graphs, claim verification, and contradiction detection.
5. DOCX/PDF report export, collaboration, and scheduled monitoring.

## License

See [LICENSE](LICENSE). This project is currently distributed under a proprietary, no-reuse license.
