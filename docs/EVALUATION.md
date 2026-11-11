# Retrieval and research evaluation

V2 introduces chunk retrieval. It should be evaluated independently from the language model so retrieval failures are not confused with generation failures.

## Baselines

- **Lexical baseline:** SQLite's bounded term-overlap ranking over a project's source chunks.
- **Semantic candidate:** PostgreSQL pgvector cosine ranking over text embeddings.
- **Generation:** compare cited answers against a fixed, human-reviewed answer key after retrieval quality is measured.

## Metrics to record

- Recall@5 and Recall@10 against human-labelled relevant source chunks.
- Mean reciprocal rank (MRR) for the first relevant chunk.
- Citation precision: fraction of cited source IDs that actually support the associated statement.
- Citation coverage: fraction of factual answer statements with a supporting citation.
- p50/p95 retrieval latency and embedding latency.
- Embedding token usage and estimated provider cost.
- Worker job completion rate, retry rate, and end-to-end collection latency.

## Reproducible protocol

1. Create a versioned evaluation set with research questions, permitted source documents, and gold relevant chunk IDs.
2. Fix chunk size, overlap, and top-k.
3. Run the lexical baseline and the semantic candidate over the exact same corpus.
4. Report each query's results and aggregate metrics.
5. Inspect failure cases: acronym mismatch, date-sensitive terms, multilingual sources, duplicated passages, low-quality metadata and contradictory studies.
6. Repeat with and without reranking before making a production claim.

No benchmark scores are reported here because the labelled evaluation set and benchmark run have not yet been completed. Do not infer a semantic-retrieval quality improvement merely from enabling pgvector.
