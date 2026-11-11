# Retrieval and evidence evaluation

V3 separates retrieval quality, claim extraction, evidence-link validity, and human review. These must be measured independently; no metric is inferred from enabling pgvector or generating a claim map.

## Retrieval baselines

- Lexical baseline: SQLite's bounded term-overlap ranking over a project's source chunks.
- Semantic candidate: PostgreSQL pgvector cosine ranking over the configured text embeddings.
- Reranking candidate: a separately evaluated reranker over the same retrieved pool, if configured.

## Evidence ledger metrics

Build a versioned, human-labelled set of research questions, candidate claims, source passages, and expected evidence relations. Report:

- Claim precision and recall against reviewed atomic claims.
- Evidence-link precision: fraction of stored support/contradiction links judged relevant by reviewers.
- Quote verification rate: fraction of linked quotations that are exact substrings of their retained source chunk. The parser enforces this mechanically for model-generated links.
- Source-reference validity: fraction of links that resolve to a source and chunk in the same project.
- Relation agreement: agreement between provisional supports / contradicts / context labels and blinded human annotation.
- Human-review agreement and adjudication rate for confirmed / rejected / unreviewed claims.
- Duplicate-claim rate and evidence coverage per claim.

## Retrieval metrics

- Recall@5 and Recall@10 against human-labelled relevant chunks.
- Mean reciprocal rank (MRR) for the first relevant chunk.
- Citation precision and citation coverage for generated answers.
- p50/p95 retrieval latency, embedding latency, token usage, and estimated provider cost.

## Reproducibility protocol

1. Freeze a corpus and record a Nexus snapshot digest.
2. Version the query/claim/evidence annotation set separately from the application code.
3. Fix chunking parameters, embedding model, retrieval depth, and reranker configuration.
4. Run lexical, semantic, and reranked variants on the same snapshot.
5. Have reviewers annotate claims and relations without seeing the model's assessment where feasible.
6. Report per-query metrics, aggregate metrics, confidence intervals, costs and failure cases.
7. Include missing context, ambiguous negation, numeric/date errors, cross-document disagreement, multilingual passages, duplicated papers and stale content in failure analysis.

## Reporting status

No benchmark numbers are published in this repository until a labelled evaluation corpus and repeatable benchmark run exist. Parser-level quote validation is a deterministic correctness check, not an evaluation of semantic support or truth.
