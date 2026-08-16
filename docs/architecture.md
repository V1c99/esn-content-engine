# Architecture

## Request flow

```mermaid
flowchart TD
    q["POST /search<br/>happy volunteers, no booze"] --> parse[parse the query]
    parse --> text["searched for:<br/>happy volunteers"]
    parse --> excl["excluded:<br/>alcohol"]
    text --> clip["CLIP text encoder<br/>ONNX, 512 numbers"]
    clip --> sql
    excl --> sql

    subgraph sql["one SQL statement"]
        elig["eligible<br/>the items not excluded"]
        elig --> sem["semantic<br/>embedding &lt;=&gt; query, HNSW"]
        elig --> lex["lexical<br/>tsvector @@ tsquery"]
        elig --> tag["tags<br/>tag_match, IDF weighted"]
        sem --> fuse["fuse by rank<br/>sum of 1/(60 + rank)"]
        lex --> fuse
        tag --> fuse
    end

    sql --> out["40 results, best moment per item"]
```

All three retrievers join `eligible`, so an excluded item cannot come back through any of
them. There is one search endpoint, see ADR-0004.

## Schema

```mermaid
erDiagram
    media ||--o{ media_embedding : "one per item, one per video second"
    media ||--o{ media_tag : ""
    media ||--o{ media_use : "recruitment, hero, opener"
    media ||--o{ media_avoid : "reputational, blurry, dark"
    media ||--o{ probe : ""
    tag ||--o{ media_tag : "document_count gives the IDF"
    probe_meta ||--o{ probe : "roc_auc, so a weak probe is marked"
```

`media_embedding` holds both levels. A photo or a whole video sits at `timestamp_s = 0`, and
a sampled video frame sits at the second it came from. The timestamp is part of the primary
key, which is what lets a search return the moment inside a clip instead of the clip.

The library has 2,334 items and 8,919 vectors: 2,334 for whole items and 6,585 video frames.

## Exclusion rules

The alcohol label records what a labeller could see in the frame, so a clip shot inside a pub
with no drink in shot passes it. A second rule matches the place and the activity instead.
Both are predicates in the `eligible` CTE.

All of the matching is word boundary only. Substring matching flagged "public" as pub,
"beginning" as gin and "barrier" as bar, which was 208 false suspects in the old engine. Two
exemptions are real cases in this library: a university "student club" room is not a
nightclub, and there are two clips of a horse drinking at a trough.

Measured on the real library: the visible-alcohol label flags 526 items, the venue rule flags
630, and 151 of those 630 are items the label alone would have missed.

## Out of scope

No Kubernetes, no message queue, no separate search service. It is one API process, one
Postgres and one Redis, and Postgres does the vector search, the keyword search and the tag
scoring in the same query. The library is 2,334 items, so none of that would earn its keep.
