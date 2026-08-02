# 3. Reciprocal rank fusion instead of weighted scores

- Date: 2026-08-02
- Status: accepted

## Context

There are three retrievers and their scores are not comparable. Cosine distance is between 0
and 2, `ts_rank_cd` is an unbounded small float that depends on document length, and the tag
score is a sum of inverse document frequencies that grows with the number of terms that
matched.

The first version normalised each of the three to 0..1 and then combined them with hand
picked weights, tag 0.50, keyword 0.22, semantic 0.28. Those weights were tuned by trying
queries and looking at the results. Every time the library grew the normalisation moved,
because it divided by the best score in the current result set.

## Decision

Reciprocal rank fusion. Each retriever contributes `1 / (k + rank)` where rank is that
retriever's own ordering, and k is 60. The three contributions are summed per item and the
sum decides the final order. It all happens in one SQL statement.

## Consequences

Good: nothing has to be normalised, because only the position matters and not the score. A
retriever that is very confident and wrong cannot dominate, it can only put one item at rank
1. There are no weights to tune and nothing to re-tune when the library grows.

Bad: the size of a gap is thrown away. If the top semantic hit is far better than the second,
RRF only sees rank 1 and rank 2. For a library of this size that has not been a problem, but
it is a real loss of information.

One change from the plain version of the query. Grouping by item and second let a 60 second
video contribute 60 rows and fill the whole page with one clip. The semantic side is now
collapsed to the best moment per item before the ranks are given out, and the timestamp of
that moment is carried through so a video result still points at the right second.
