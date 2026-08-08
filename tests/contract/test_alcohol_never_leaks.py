"""The exclusion rules, checked against the items that used to break them.

Six of these are word matching traps that were live bugs. Bare substring matching produced
208 false suspects in the old engine, so all the venue matching is word boundary only.
"""

import pytest
from sqlalchemy import text

from esn_engine.core.config import Settings
from esn_engine.search import exclusions, fusion, query
from tests import helpers

pytestmark = [pytest.mark.contract, pytest.mark.needs_postgres]

# Which of the seeded items the venue rule is allowed to flag.
VENUE_ITEMS = {7, 8}
NOT_VENUE_ITEMS = {1, 2, 3, 4, 5, 6, 9, 10, 11, 12}


async def flagged_ids(session) -> set[int]:
    """The ids the two alcohol rules flag, straight out of the SQL."""
    # The two predicates are module constants, nothing here comes from a request.
    statement = f"""
        SELECT media.id FROM media
        WHERE {exclusions.ALCOHOL.predicate}
           OR {exclusions.VENUE.predicate}
    """  # noqa: S608
    rows = await session.execute(text(statement))
    return {r.id for r in rows}


async def search_for(session, raw: str, near_item: int, settings: Settings):
    parsed = query.parse(raw)
    return await fusion.search(session, parsed, helpers.unit_vector(near_item), settings)


async def test_a_public_square_is_not_a_pub(session):
    """The word public contains pub. Bare substring matching flagged it."""
    assert 1 not in await flagged_ids(session)


async def test_the_beginning_of_a_hike_is_not_gin(session):
    """The word beginning contains gin."""
    assert 2 not in await flagged_ids(session)


async def test_a_crowd_barrier_is_not_a_bar(session):
    """The word barrier contains bar."""
    assert 3 not in await flagged_ids(session)


async def test_a_student_club_room_is_not_a_drinking_venue(session):
    """A university society room matches club but nobody is drinking in it."""
    assert 4 not in await flagged_ids(session)


async def test_a_horse_drinking_at_a_trough_is_not_a_bar(session):
    """The activity says drinking and it is a horse."""
    assert 5 not in await flagged_ids(session)


async def test_camera_shots_are_not_drinks(session):
    """In this library the word shots nearly always means camera shots."""
    assert 6 not in await flagged_ids(session)


async def test_the_venue_rule_still_flags_a_real_bar(session):
    """The exemptions above must not have turned the rule off entirely."""
    flagged = await flagged_ids(session)
    assert flagged >= VENUE_ITEMS
    assert not (flagged & NOT_VENUE_ITEMS)


async def test_a_no_booze_brief_returns_nothing_shot_in_a_bar(session, settings):
    """The label only records visible alcohol. 19 clips shot in a pub got through before."""
    result = await search_for(session, "socialising, no booze", near_item=7, settings=settings)
    returned = {h.media_id for h in result.hits}
    assert not (returned & VENUE_ITEMS)
    assert "alcohol-venue" in result.applied_exclusions
