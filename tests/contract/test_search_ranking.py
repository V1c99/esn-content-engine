"""How the three retrievers get combined, and what must not happen while combining them."""

import pytest
from sqlalchemy import text

from esn_engine.search import fusion, query
from tests import helpers

pytestmark = [pytest.mark.contract, pytest.mark.needs_postgres]

LONG_CLIP = 12
# The frame of the long clip that sits somewhere else in the space.
ODD_FRAME_SECOND = 41.0
ODD_FRAME_SEED = 99


async def test_one_long_video_cannot_fill_the_whole_page(session, settings):
    """The clip has 40 frames on the same spot. Grouping by (item, second) returned all 40."""
    parsed = query.parse("courtyard")
    result = await fusion.search(session, parsed, helpers.unit_vector(LONG_CLIP), settings)
    appearances = [h.media_id for h in result.hits].count(LONG_CLIP)
    assert appearances == 1, f"the long clip came back {appearances} times"


async def test_a_video_hit_reports_the_second_that_matched(session, settings):
    """A reel needs the moment, not the file. One frame is near this query, at 41 seconds."""
    parsed = query.parse("courtyard")
    result = await fusion.search(session, parsed, helpers.unit_vector(ODD_FRAME_SEED), settings)
    hit = next(h for h in result.hits if h.media_id == LONG_CLIP)
    assert hit.timestamp_s == ODD_FRAME_SECOND


async def test_results_come_back_ordered_by_fused_score(session, settings):
    parsed = query.parse("volunteers")
    result = await fusion.search(session, parsed, helpers.unit_vector(10), settings)
    scores = [h.rrf_score for h in result.hits]
    assert scores == sorted(scores, reverse=True)


async def test_a_rarer_tag_is_worth_more_than_a_common_one(session):
    """tag_match weights by IDF. A tag on every item should not decide the ranking."""
    rare = await session.execute(
        text("SELECT idf_weighted_score FROM tag_match('shelter') WHERE media_id = 11")
    )
    common = await session.execute(
        text("SELECT idf_weighted_score FROM tag_match('animals') WHERE media_id = 11")
    )
    counts = await session.execute(
        text("SELECT term, document_count FROM tag WHERE term IN ('shelter', 'animals')")
    )
    by_term = {r.term: r.document_count for r in counts}
    assert by_term["shelter"] < by_term["animals"]
    assert rare.scalar() > common.scalar()


async def test_the_result_limit_is_respected(session, settings):
    parsed = query.parse("volunteers")
    small = settings.model_copy(update={"result_limit": 3})
    result = await fusion.search(session, parsed, helpers.unit_vector(10), small)
    assert len(result.hits) == 3


async def test_a_kind_word_filters_the_results(session, settings):
    """Asking for clips must not return photos."""
    parsed = query.parse("clips of the courtyard")
    assert parsed.kind == "video"
    result = await fusion.search(session, parsed, helpers.unit_vector(LONG_CLIP), settings)
    ids = [h.media_id for h in result.hits]
    kinds = await session.execute(
        text("SELECT DISTINCT kind FROM media WHERE id = ANY(:ids)"), {"ids": ids}
    )
    assert {r.kind for r in kinds} == {"video"}
