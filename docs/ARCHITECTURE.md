# Architecture notes

## Current request flow

1. The browser creates a research project through `POST /api/projects`.
2. The browser starts a collection run through `POST /api/projects/{id}/research`.
3. `run_research` fans out to enabled provider adapters concurrently.
4. Provider responses are normalized and deduplicated by URL.
5. Normalized source records are persisted in SQLite and surfaced in the workspace.
6. Chat/report services rank available sources with lightweight lexical overlap, then pass excerpts and stable source IDs to the configured model.
7. If no model key is configured, the app deliberately falls back to extractive snippets and labels the result as a fallback.

## Why the first version uses SQLite

SQLite makes the project easy to run locally and keeps setup small while the product workflow is being validated. It is not the intended multi-user production store. The planned production migration is PostgreSQL with ownership policies, full-text indexes and pgvector for semantic retrieval.

## Research integrity requirements

- A source's original URL and provider metadata must be retained.
- Every answer claim that depends on collected evidence should cite source IDs.
- A report must distinguish evidence, synthesis, uncertainty and missing coverage.
- Provider errors and missing credentials must be visible; a failed connector must not be represented as a comprehensive search.
- Source ranking must not be mistaken for source credibility. Credibility scoring needs explicit signals and human review.
