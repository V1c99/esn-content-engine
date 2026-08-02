"""The search. Three retrievers, fused by rank, in one SQL statement."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from esn_engine.core.config import Settings
from esn_engine.search.exclusions import BY_CONCEPT, SAFETY_FLOOR, Exclusion
from esn_engine.search.query import ParsedQuery


@dataclass(frozen=True)
class Hit:
    media_id: int
    # For a video, the second the best matching frame was sampled from. 0 for a photo.
    timestamp_s: float
    rrf_score: float


@dataclass(frozen=True)
class SearchResult:
    hits: tuple[Hit, ...]
    # The rule names that were applied, so the interface can show them.
    applied_exclusions: tuple[str, ...]
    safety_floor: bool


# Every retriever joins `eligible`, so an excluded item cannot come back through any of them.
# See docs/adr/0004.
#
# The semantic side is collapsed to one row per item before ranking, otherwise a 60 second
# video contributes 60 frames and one clip fills the page.
SEARCH_SQL = """
WITH eligible AS (
    SELECT media.id
    FROM media
    WHERE {eligible_where}
),
nearest AS (
    SELECT e.media_id, e.timestamp_s, e.embedding <=> CAST(:qvec AS vector) AS distance
    FROM media_embedding e
    JOIN eligible ON eligible.id = e.media_id
    ORDER BY e.embedding <=> CAST(:qvec AS vector)
    LIMIT :frame_scan
),
semantic AS (
    SELECT media_id, timestamp_s, ROW_NUMBER() OVER (ORDER BY distance) AS rank
    FROM (
        SELECT DISTINCT ON (media_id) media_id, timestamp_s, distance
        FROM nearest
        ORDER BY media_id, distance
    ) best_moment
    ORDER BY rank
    LIMIT :candidates
),
lexical AS (
    SELECT media.id AS media_id,
           0::double precision AS timestamp_s,
           ROW_NUMBER() OVER (
               ORDER BY ts_rank_cd(media.search_vector,
                                   websearch_to_tsquery('english', :q)) DESC
           ) AS rank
    FROM media
    JOIN eligible ON eligible.id = media.id
    WHERE media.search_vector @@ websearch_to_tsquery('english', :q)
    LIMIT :candidates
),
tags AS (
    SELECT t.media_id,
           0::double precision AS timestamp_s,
           ROW_NUMBER() OVER (ORDER BY t.idf_weighted_score DESC) AS rank
    FROM tag_match(:q) t
    JOIN eligible ON eligible.id = t.media_id
    LIMIT :candidates
),
fused AS (
    SELECT media_id,
           SUM(1.0 / (:rrf_k + rank)) AS rrf_score,
           -- The lexical and tag rows carry 0, so this picks the semantic timestamp when
           -- there is one.
           MAX(timestamp_s) AS timestamp_s
    FROM (
        SELECT * FROM semantic
        UNION ALL SELECT * FROM lexical
        UNION ALL SELECT * FROM tags
    ) parts
    GROUP BY media_id
)
SELECT media_id, timestamp_s, rrf_score
FROM fused
ORDER BY rrf_score DESC, media_id
LIMIT :result_limit
"""


def rules_for(parsed: ParsedQuery) -> tuple[Exclusion, ...]:
    """Which exclusion rules a query turns into.

    The safety floor is added whenever anything at all is excluded. Somebody who says "no
    booze" does not want the clip of a volunteer face down in the street either.
    """
    rules: list[Exclusion] = []
    for concept in parsed.excluded:
        for rule in BY_CONCEPT.get(concept, ()):
            if rule not in rules:
                rules.append(rule)
    if rules:
        rules.append(SAFETY_FLOOR)
    return tuple(rules)


def _eligible_where(parsed: ParsedQuery, rules: tuple[Exclusion, ...]) -> str:
    parts = ["TRUE"]
    if parsed.kind is not None:
        parts.append("media.kind = :kind")
    parts.extend(f"NOT {rule.predicate}" for rule in rules)
    return "\n      AND ".join(parts)


async def search(
    session: AsyncSession,
    parsed: ParsedQuery,
    query_vector: list[float],
    settings: Settings,
) -> SearchResult:
    rules = rules_for(parsed)
    statement = SEARCH_SQL.format(eligible_where=_eligible_where(parsed, rules))

    params: dict[str, object] = {
        "q": parsed.text,
        # pgvector accepts the literal text form, which avoids registering a codec on the
        # asyncpg connection.
        "qvec": "[" + ",".join(f"{x:.6f}" for x in query_vector) + "]",
        "rrf_k": settings.rrf_k,
        "candidates": settings.candidate_limit,
        # Deeper than the candidate limit because the frames of one clip sit next to each
        # other, so the first 200 rows can easily be four videos.
        "frame_scan": settings.candidate_limit * 4,
        "result_limit": settings.result_limit,
        "floor_flags": list(settings.safety_floor_flags),
    }
    if parsed.kind is not None:
        params["kind"] = parsed.kind

    rows = await session.execute(text(statement), params)
    hits = tuple(
        Hit(
            media_id=r.media_id,
            timestamp_s=float(r.timestamp_s),
            rrf_score=float(r.rrf_score),
        )
        for r in rows
    )
    return SearchResult(
        hits=hits,
        applied_exclusions=tuple(rule.name for rule in rules),
        safety_floor=any(rule is SAFETY_FLOOR for rule in rules),
    )
