# Nexus Research

Nexus Research is a source-grounded workspace for collecting evidence from multiple providers, asking questions across a research library, and producing cited reports.

**Version 3** adds a claim-level evidence ledger, auditable source-passage links, researcher review decisions, and content-addressed research snapshots on top of V2's secure workspaces and durable collection pipeline.

## What works in V3

- **Accounts and isolation:** sign up/sign in with Argon2 password hashes, HttpOnly session cookies, CSRF validation, and owner-scoped project/source/message/report/job reads and writes.
- **Research projects:** create independent research workspaces with a question, source library, chat history and saved reports.
- **Source collection:** OpenAlex, Crossref, arXiv and GDELT work without keys; Brave Search, YouTube Data API and X require provider credentials.
- **Background research:** requests are stored as database jobs and processed by a separate worker. Jobs survive API restarts, retry failures, and recover stale worker leases.
- **Evidence indexing:** imported material is chunked with overlap. PostgreSQL uses pgvector cosine search when OpenAI embeddings are configured; SQLite uses bounded lexical retrieval for local development.
- **Research chat and reports:** model-powered responses cite source IDs and are instructed to treat source text as untrusted evidence. Without an LLM key, the app labels its output as an extractive fallback.
- **Document imports:** PDF, DOCX, TXT, Markdown and public readable webpages.
- **Exports:** Markdown, DOCX and PDF.
- **Evidence ledger:** extractive claim candidates or optional structured LLM mapping, with exact stored passage excerpts linked by source and chunk ID.
- **Evidence review:** source relationships are labelled as support, contradiction or context; human review state is separate from machine assessment.
- **Research snapshots:** capture a manifest with SHA-256 hashes for stored source text and a canonical corpus digest; unchanged corpora resolve to the same snapshot record.
- **Operations:** Docker Compose with PostgreSQL/pgvector, a separate worker, and Alembic schema migration.

## Quick start: local development

Requirements: Python 3.11+.

### 1. Create the environment

Windows PowerShell:

    python -m venv .venv
    .venv\Scripts\Activate.ps1
    Copy-Item .env.example .env
    pip install -r requirements-dev.txt

macOS/Linux:

    python -m venv .venv
    source .venv/bin/activate
    cp .env.example .env
    pip install -r requirements-dev.txt

For local development, SQLite is selected automatically when DATABASE_URL is not set. Set a unique SESSION_SECRET_KEY in .env before using real data. An OpenAI key is optional.

### 2. Start the API

    uvicorn app.main:app --app-dir backend --reload

Open http://127.0.0.1:8000 and create an account.

### 3. Start the background worker

In a second terminal, activate the same virtual environment and run:

Windows PowerShell:

    $env:PYTHONPATH="backend"; python -m app.worker

macOS/Linux:

    PYTHONPATH=backend python -m app.worker

The API persists jobs; the worker performs provider collection and indexing. Keep both processes running for research collection.

## Run with PostgreSQL + pgvector

1. Copy .env.example to .env.
2. Set a strong POSTGRES_PASSWORD and generate a long random SESSION_SECRET_KEY.
3. Add provider and LLM keys as required.
4. Run: docker compose up --build

The API container runs Alembic migrations before starting. The worker waits for the API and database to start. PostgreSQL data is stored in the nexus-postgres Docker volume.

For HTTPS deployment, set AUTH_COOKIE_SECURE=true, terminate TLS at a trusted reverse proxy, and configure request-size limits and rate limiting at the edge.

## Configuration

| Variable | Purpose |
|---|---|
| SESSION_SECRET_KEY | Required for production cookie signing and CSRF signatures |
| AUTH_COOKIE_SECURE | Set true when served over HTTPS |
| SESSION_TTL_HOURS | Session lifetime; defaults to 12 hours |
| DATABASE_URL | SQLAlchemy URL; PostgreSQL recommended for deployment |
| OPENAI_API_KEY | Enables model-powered synthesis and embeddings |
| OPENAI_MODEL | Chat model; defaults to gpt-4.1-mini |
| OPENAI_EMBEDDING_MODEL | Defaults to text-embedding-3-small (1536 dimensions) |
| BRAVE_SEARCH_API_KEY | Optional web search connector |
| YOUTUBE_API_KEY | Optional YouTube Data API connector |
| X_BEARER_TOKEN | Optional X recent-search connector |
| NEXUS_CONTACT_EMAIL | Optional contact address for academic API polite pools |

Keys are read server-side. Never put provider secrets in frontend JavaScript or commit a populated .env.

## Tests

    pip install -r requirements-dev.txt
    pytest -q

The test suite covers authentication, owner isolation, CSRF-protected writes, durable queue state transitions, source indexing, document export and URL safety. CI also compiles Python modules and checks frontend JavaScript syntax.

## Architecture

    Browser
      ├── HttpOnly session + CSRF token
      └── FastAPI
            ├── Auth + owner-scoped API
            ├── PostgreSQL / SQLite
            │     ├── users, projects, sources, chunks
            │     ├── messages, reports
            │     └── durable research jobs
            ├── Provider adapters
            ├── Chunking + embedding + retrieval
            └── Report generation
                     ▲
                     │
            Background worker
            ├── claim queued job
            ├── collect providers
            ├── deduplicate and persist
            ├── chunk and embed
            └── complete / retry / recover

See docs/ARCHITECTURE.md, docs/CONNECTORS.md, docs/OPERATIONS.md, docs/EVALUATION.md, and docs/EVIDENCE_LEDGER.md.

## V3 evidence and reproducibility notes

- Extractive mode stores sentences as **context-only candidates**. It does not infer that an extracted sentence is supported, verified, or true.
- Optional model links are accepted only when source IDs and chunk indexes exist in the same project and the quoted passage is found verbatim in the stored chunk.
- Model assessments remain provisional. Researchers explicitly mark a claim confirmed, rejected, or unreviewed.
- Snapshot digests represent the stored corpus and project metadata at capture time. They do not prove a publisher page has not changed elsewhere, nor do they certify the truth of any claim.
- A snapshot is a reproducibility manifest, not an immutable third-party archive. Original source URLs remain the authoritative publisher records.

## Important limitations

- Instagram and Facebook connectors are not implemented. Use only supported Meta APIs and permissions; the product does not bypass logins or scrape private accounts.
- YouTube discovery returns metadata; transcript retrieval is not included.
- Google Scholar has no unrestricted bulk API integration; scholarly discovery uses OpenAlex, Crossref and arXiv.
- Semantic retrieval requires a configured embedding provider and PostgreSQL/pgvector. SQLite uses lexical retrieval.
- Email verification, password reset, OAuth sign-in, MFA, team collaboration and organization-level access controls are not included yet.
- Public deployment still requires operational rate limiting, backups, monitoring, HTTPS, secret rotation, and a security review. Do not treat an MVP as an audited security product.
- Search coverage depends on provider quotas, API tiers, content permissions and source availability. The system must not claim exhaustive coverage.

## Version 2 migration note

V2 uses a new SQLite filename at backend/data/nexus-v2.db for local development. It does not silently reuse or migrate the V1 SQLite database. Export any V1 material you need before switching; an explicit V1-to-V2 migration utility is a future task.

## License

See LICENSE. This repository is distributed under a proprietary, no-reuse license.
