# V3 evidence ledger guide

## What the ledger is for

The ledger turns a research library into reviewable claims. Instead of returning only a generated paragraph, Nexus stores claim candidates and the source passages associated with each candidate.

## How to use it

1. Collect sources or upload documents to a project.
2. Open the Evidence ledger tab and choose Analyze evidence.
3. Inspect each candidate and open the cited original source when a public URL is available.
4. Read every stored passage. Use Confirm only when the passage and full source context support the claim; use Reject when it does not.
5. Capture a research snapshot after completing a collection or review milestone. Use View manifest to download its JSON record.

## Interpretation rules

- needs_review: no validated semantic conclusion has been established.
- support_indicated: a model linked one or more passages as supporting evidence.
- contradicted: a model linked one or more passages as contradictory evidence.
- contested: the model identified both support and contradictory passages.
- context: the passage is the exact context for an extractive sentence or does not have a verified direction.

These are workflow signals, not truth labels. Model analysis may miss nuance, negation, scope, population differences, definitions, or study limitations. A claim should not be cited as established merely because a badge says support indicated.

## Snapshot contents

The manifest stores project metadata, source identifiers and metadata, content character counts, SHA-256 hashes of stored source text, the indexed chunk count, and an integrity note. The canonical digest excludes capture time, so an unchanged corpus yields the same digest.

A hash proves only that a future comparison can detect a change in the hashed stored content. It does not prove a publisher's page was captured completely, is authentic, or has not changed outside Nexus.

## Suggested human annotation schema

For evaluation, annotate each candidate with:
- atomic claim text;
- source ID and chunk index;
- relation (supports, contradicts, context, irrelevant);
- whether the quote is exact;
- whether the complete source context changes interpretation;
- reviewer confidence and an explanation.

Use two independent reviewers and adjudicate disagreements before publishing benchmark results.
