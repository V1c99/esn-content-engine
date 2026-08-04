"""The HTTP routes."""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from esn_engine.api.deps import ServicesDep, SessionDep
from esn_engine.api.schemas import (
    HitOut,
    Interpretation,
    MediaDetail,
    MediaOut,
    ProbeOut,
    ProbeScoreOut,
    SearchRequest,
    SearchResponse,
    TagOut,
)
from esn_engine.core.cache import key_for
from esn_engine.probes.quality import is_weak
from esn_engine.search import fusion, query

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """Only says the process is up.

    The container healthcheck calls this. If it also checked Postgres then a database restart
    would make Docker kill an API that was working fine.
    """
    return {"status": "ok"}


@router.post("/search")
async def search(
    request: SearchRequest, services: ServicesDep, session: SessionDep
) -> SearchResponse:
    """One search. There is no second endpoint for briefs, see docs/adr/0004."""
    started = time.perf_counter()

    settings = services.settings
    if request.limit is not None:
        settings = settings.model_copy(update={"result_limit": request.limit})

    cache_key = key_for(request.q, settings.result_limit)
    cached = await services.cache.get(cache_key)
    if cached is not None:
        answer = SearchResponse.model_validate_json(cached)
        return answer.model_copy(
            update={"cached": True, "took_ms": int((time.perf_counter() - started) * 1000)}
        )

    parsed = query.parse(request.q)

    vector = services.encoder.embed_one(parsed.text)
    result = await fusion.search(session, parsed, vector, settings)
    media = await _media_by_id(session, [h.media_id for h in result.hits])

    hits = tuple(
        HitOut(media=media[h.media_id], timestamp_s=h.timestamp_s, rrf_score=h.rrf_score)
        for h in result.hits
        if h.media_id in media
    )
    answer = SearchResponse(
        interpretation=Interpretation(
            query=request.q,
            searched_for=parsed.text,
            kind=parsed.kind,
            excluded_concepts=parsed.excluded,
            applied_rules=result.applied_exclusions,
            safety_floor=result.safety_floor,
            dropped_words=parsed.dropped,
        ),
        hits=hits,
        took_ms=int((time.perf_counter() - started) * 1000),
    )
    await services.cache.set(cache_key, answer.model_dump_json(), settings.cache_ttl_seconds)
    return answer


@router.get("/media/{media_id}")
async def read_media(media_id: int, session: SessionDep) -> MediaDetail:
    row = (
        await session.execute(
            text("""SELECT id, name, event, kind, width, height, duration_s, shot_at,
                            place, activity, alcohol_visible, description, indoor_outdoor,
                            time_of_day, people_count, emotion
                     FROM media WHERE id = :id"""),
            {"id": media_id},
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no media {media_id}")

    uses = await session.scalars(
        text("SELECT use FROM media_use WHERE media_id = :id ORDER BY use"), {"id": media_id}
    )
    avoid = await session.scalars(
        text("SELECT flag FROM media_avoid WHERE media_id = :id ORDER BY flag"), {"id": media_id}
    )
    # Rarest tags first, they say the most about the item.
    tags = await session.execute(
        text("""SELECT mt.term, mt.source, mt.weight
                FROM media_tag mt JOIN tag t ON t.term = mt.term
                WHERE mt.media_id = :id
                ORDER BY t.document_count ASC, mt.term
                LIMIT 40"""),
        {"id": media_id},
    )
    probes = await session.execute(
        text("""SELECT p.name, p.p, m.roc_auc
                FROM probe p JOIN probe_meta m ON m.name = p.name
                WHERE p.media_id = :id
                ORDER BY p.p DESC"""),
        {"id": media_id},
    )

    return MediaDetail(
        media=_media_out(row),
        description=row.description,
        indoor_outdoor=row.indoor_outdoor,
        time_of_day=row.time_of_day,
        people_count=row.people_count,
        emotion=row.emotion,
        uses=tuple(uses),
        avoid=tuple(avoid),
        tags=tuple(TagOut(term=t.term, source=t.source, weight=t.weight) for t in tags),
        probes=tuple(
            ProbeScoreOut(name=p.name, p=p.p, roc_auc=p.roc_auc, weak=is_weak(p.roc_auc))
            for p in probes
        ),
    )


@router.get("/probes")
async def list_probes(session: SessionDep) -> list[ProbeOut]:
    """The 23 probes with the accuracy each one was measured at."""
    rows = await session.execute(
        text("""SELECT name, roc_auc, average_precision, n_positive
                FROM probe_meta ORDER BY roc_auc DESC""")
    )
    return [
        ProbeOut(
            name=r.name,
            roc_auc=r.roc_auc,
            average_precision=r.average_precision,
            n_positive=r.n_positive,
            weak=is_weak(r.roc_auc),
        )
        for r in rows
    ]


@router.get("/suggest")
async def suggest(session: SessionDep, q: str = Query(min_length=1, max_length=60)) -> list[str]:
    """Type-ahead over the tag vocabulary. Prefix matches first, then anything containing it."""
    rows = await session.scalars(
        text("""SELECT term FROM tag
                WHERE term LIKE :prefix OR term LIKE :anywhere
                ORDER BY (term LIKE :prefix) DESC, document_count DESC
                LIMIT 12"""),
        {"prefix": f"{q.lower()}%", "anywhere": f"%{q.lower()}%"},
    )
    return list(rows)


def _media_out(row: object) -> MediaOut:
    return MediaOut.model_validate(row, from_attributes=True)


async def _media_by_id(session: AsyncSession, ids: list[int]) -> dict[int, MediaOut]:
    if not ids:
        return {}
    rows = await session.execute(
        text("""SELECT id, name, event, kind, width, height, duration_s, shot_at,
                        place, activity, alcohol_visible
                 FROM media WHERE id = ANY(:ids)"""),
        {"ids": ids},
    )
    return {r.id: _media_out(r) for r in rows}
