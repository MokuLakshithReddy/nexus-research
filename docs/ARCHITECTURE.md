# Nexus Research V3 architecture

## System flow

1. A user authenticates and creates a private, owner-scoped research project.
2. A durable research job is claimed by a worker. Enabled provider adapters collect metadata and available text.
3. Sources are deduplicated, persisted, split into overlapping chunks, and embedded when a configured embedding provider is available.
4. Retrieval returns source and chunk identifiers with excerpts. PostgreSQL uses pgvector when configured; SQLite retains a bounded lexical fallback.
5. Research chat and report drafting use retrieved evidence, preserve source identifiers and treat all imported text as untrusted data.
6. The V3 evidence analyzer creates candidate factual claims. With an LLM key it requests structured support/contradiction/context links; without one, it extracts sentences and labels their links as context only.
7. A validator rejects invented source/chunk identifiers and model quotations that do not occur verbatim in the associated stored chunk.
8. The evidence ledger stores each candidate, provisional machine assessment, source-passage links, and a separate researcher review status.
9. A researcher can capture a content-addressed snapshot containing the project metadata, source metadata, SHA-256 source-text hashes, and indexed chunk count.

## Evidence ledger

The evidence_claims table stores project-scoped, deduplicated claim candidates. The claim_evidence table links a claim to a source passage through (source_id, chunk_index). The database validates that the source and chunk belong to the same project before a link is saved.

Relations have three values:

- supports: the provisional analyzer says this passage supports the claim.
- contradicts: the provisional analyzer says this passage conflicts with the claim.
- context: passage is the exact context for an extractive candidate, or the analyzer cannot assign a stronger relation.

Machine assessment is distinct from researcher review. Review values are unreviewed, confirmed, and rejected. Re-running analysis may refresh machine assessment and links but must not overwrite the review decision.

Extractive fallback always uses needs_review plus context; it does not call a matching sentence verified.

## Structured model output validation

The model is asked for JSON containing claims and exact quotes. The parser:
- limits claim and evidence counts;
- checks each source ID and chunk index against the current project's supplied chunks;
- accepts only supports, contradicts, or context;
- requires a verbatim quote substring of at least 24 characters in the stored chunk;
- drops claims without at least one valid evidence link;
- falls back to extractive contextual candidates if the model response is malformed or yields no valid claims.

This validator improves traceability but does not establish semantic entailment. Researchers must inspect the original source.

## Research snapshots

A snapshot is a canonical manifest with project details and source records. Each source record includes a SHA-256 hash of its stored content. A canonical JSON payload excluding the capture timestamp is hashed to provide deterministic identity for an unchanged research state. Repeated captures of an unchanged corpus return the existing snapshot record.

The digest does not prove third-party publisher content is unchanged, and no external webpage is mirrored as an immutable archive by this feature.

## Persistence and migration

V3 adds evidence_claims, claim_evidence, and research_snapshots through Alembic revision 0002_v3_evidence, after 0001_v2_schema. The migration checks existing tables/indexes because the V2 baseline migration uses SQLAlchemy metadata creation on new installations.

V2 accounts, projects, sources, chunks, queue jobs, messages, and reports are preserved. No V1-to-V2 migration is implied.

## Security boundaries

- All V3 routes require the authenticated owner-scoped project.
- All state-changing routes require the existing CSRF token.
- Evidence links are only created against source/chunk rows belonging to that project.
- Model-generated source IDs, passage quotes, and relations are treated as untrusted until validated.
- Source text is never executed. Prompt instructions inside source documents are ignored.
- Snapshot hashes cover stored content and canonical metadata; they are integrity fingerprints, not trust or authenticity certificates.
