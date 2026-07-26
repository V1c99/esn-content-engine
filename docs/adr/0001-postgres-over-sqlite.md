# 1. PostgreSQL with pgvector over SQLite FTS5

- Date: 2026-07-26
- Status: accepted

## Context

The first version used SQLite with FTS5 for the keyword search and kept the CLIP embeddings
in a NumPy array that was loaded into memory when the process started. It worked for one
person on one laptop.

Two problems showed up. The semantic results and the keyword results had to be merged in
Python, which meant two code paths that could drift apart, and they did drift, see ADR-0004.
And the array was loaded per process, so running more than one worker meant holding the same
2,334 vectors in memory twice.

## Decision

PostgreSQL 17 with the pgvector extension. The embeddings live in a `vector(512)` column with
an HNSW index using cosine distance. The keyword search uses a `tsvector` column with a GIN
index. Both are read in one statement and fused with reciprocal rank fusion in SQL.

## Consequences

Good: one retrieval path, so the bug in ADR-0004 cannot happen again by construction.
Several readers at once. Schema changes are versioned through Alembic instead of being a
migration script somebody remembers to run.

Bad: `docker compose up` is now needed to run the project, where before it was a single
Python process. Anybody who wants to contribute needs Docker.

HNSW is approximate, so it is not guaranteed to return exactly what an exhaustive scan would.
I measured it on 200 random queries at k=40 against the same query with index scans turned
off: mean recall 0.9958, worst case 0.950, and 170 of the 200 were identical. The index takes
a median of 3.3 ms where the exhaustive scan takes 18.3 ms. Losing about half a percent of
recall for that is worth it here.
