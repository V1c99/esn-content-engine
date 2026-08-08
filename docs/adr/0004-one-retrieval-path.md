# 4. One retrieval path

- Date: 2026-08-08
- Status: accepted

## Context

The old engine had two search endpoints. `/api/query` took a brief and applied the exclusion
rules, and `/api/search` was the typo tolerant hybrid search added later, which had no
negation handling at all.

They gave different answers to the same question. `/api/ask` dropped items flagged
`reputational` or `unusable` whenever a brief excluded anything. `/api/query` did not, and
`/api/query` was the one the interface actually called, so the interface was the more
permissive of the two. The handoff notes for that version say, in as many words, do not route
briefs through `/api/search` because it would leak.

Neither filter was wrong on its own. There were just two places to remember it and only one
of them had it.

## Decision

One endpoint, `POST /search`, and one SQL statement. The statement starts with an `eligible`
CTE that computes the allowed items once, and all three retrievers join it. The safety floor
is applied whenever the query excludes anything at all.

An exclusion has to be expressible as SQL over the media table to exist.

## Consequences

Good: an excluded item cannot come back through the semantic, keyword or tag retriever,
because none of them can see it. There is no second endpoint to keep in step. A contract test
asserts there is only one search route, so adding `/ask` back fails the build.

Across five briefs that exclude alcohol, the visible-alcohol label on its own let 81 items
that were shot in a bar or a club into the top 40. With the venue rule in the same statement
it is 0. On one brief, "people dancing, no booze", all 40 results were venue items before the
rule.

Bad: an exclusion that cannot be written as SQL cannot be supported. Anything needing a model
call per candidate does not fit this shape, and it would have to be a filter after the query,
which is the second path this ADR removes.
