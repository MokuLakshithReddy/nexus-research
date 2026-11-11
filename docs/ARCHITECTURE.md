# Nexus Research V2 architecture

## System flow

1. A user signs in; the browser receives an HttpOnly session cookie and a signed, readable CSRF cookie.
2. Authenticated project routes derive owner_id from the verified session. The API never trusts an owner ID from the request body.
3. The API creates a durable research_jobs row and returns a job ID immediately.
4. A separate worker claims queued jobs, calls enabled provider adapters concurrently, deduplicates URLs, persists sources, chunks source content and creates embeddings when configured.
5. The worker marks the job completed or failed. Jobs that exceed their retry count are marked failed; stale running jobs are recovered after a lease timeout.
6. Chat and report requests retrieve relevant source chunks. PostgreSQL uses pgvector cosine distance; SQLite uses a bounded lexical fallback.
7. LLM output is instructed to cite source IDs, treat source text as untrusted data, and distinguish evidence from interpretation.
8. Reports can be downloaded as Markdown, DOCX or PDF.

## Persistence

SQLAlchemy models represent users, projects, sources, source chunks, messages, reports and research jobs. PostgreSQL is the deployment target; SQLite is supported for single-machine development and tests.

All child entities are accessed through owner-scoped project joins or owner-scoped job lookups. A project ID belonging to another account returns 404.

## Background queue

The queue is database-backed rather than process-memory-backed. This means API restarts do not discard pending jobs. Workers claim one job in a short transaction and mark it running. Provider operations happen after the claim transaction closes. The worker stores attempt counts and error details, retries up to three times, and recovers stale running rows on startup.

For multiple worker replicas, PostgreSQL row locking with FOR UPDATE SKIP LOCKED allows workers to claim different jobs. SQLite is intended for one local worker.

## Retrieval

Each source is split into overlapping character-bounded chunks. When OPENAI_API_KEY is configured, chunks and queries are embedded with the configured embedding model. PostgreSQL stores vectors in pgvector and ranks by cosine distance. The SQLite path stores no vector and performs bounded lexical ranking over the project's chunks.

The initial retrieval design is intentionally transparent: source IDs, chunk indexes, source titles, dates and canonical URLs remain attached to every retrieved passage. A source's retrieval score is not a source-credibility score.

## Security boundaries

- Session cookies are HttpOnly, SameSite=Lax and configurable as Secure.
- Mutating authenticated API routes require a signed double-submit CSRF token.
- Passwords are hashed using Argon2 via pwdlib.
- Every data path is scoped to the current user.
- API keys stay server-side.
- Imported webpages reject local/private/reserved addresses and redirects. Deployments should still enforce outbound network controls to mitigate DNS rebinding and other SSRF edge cases.
- Source text is untrusted; prompt instructions explicitly prevent source content from being treated as operational instructions.

## Deliberate non-goals in V2

No unrestricted social-media scraping, no login bypass, no private-account collection, no autonomous account actions, and no claim of exhaustive internet coverage.
