"""There is one search. See docs/adr/0004.

The old engine had two endpoints. One carried the venue rule and the safety floor, the other
did not, and the interface called the permissive one. Same brief, two different answers.
"""

import pytest

from esn_engine.api.routes import router
from esn_engine.search import fusion, query
from tests import helpers

pytestmark = pytest.mark.contract

REPUTATIONAL_ITEM = 9
BAR_ITEM = 7


def test_there_is_only_one_search_endpoint():
    """Adding a second search route is how the two answers happened in the first place."""
    paths = [getattr(route, "path", "") for route in router.routes]
    searchy = {p for p in paths if any(w in p for w in ("search", "query", "ask", "brief"))}
    assert searchy == {"/search"}, f"expected one search route, found {searchy}"


@pytest.mark.needs_postgres
async def test_the_safety_floor_applies_whenever_anything_is_excluded(session, settings):
    parsed = query.parse("street at night, no booze")
    result = await fusion.search(session, parsed, helpers.unit_vector(REPUTATIONAL_ITEM), settings)
    assert result.safety_floor is True
    assert "safety-floor" in result.applied_exclusions
    assert REPUTATIONAL_ITEM not in {h.media_id for h in result.hits}


@pytest.mark.needs_postgres
async def test_the_safety_floor_is_off_when_nothing_is_excluded(session, settings):
    """A plain search is not a brief. Somebody looking for that clip has to be able to find it."""
    parsed = query.parse("street at night")
    result = await fusion.search(session, parsed, helpers.unit_vector(REPUTATIONAL_ITEM), settings)
    assert result.safety_floor is False
    assert result.applied_exclusions == ()
    assert REPUTATIONAL_ITEM in {h.media_id for h in result.hits}


@pytest.mark.needs_postgres
async def test_the_same_query_with_and_without_a_negation_differs_only_by_the_exclusion(
    session, settings
):
    """The difference has to come from the query, not from which endpoint was called."""
    plain = await fusion.search(
        session, query.parse("socialising in a bar"), helpers.unit_vector(BAR_ITEM), settings
    )
    brief = await fusion.search(
        session,
        query.parse("socialising in a bar, no booze"),
        helpers.unit_vector(BAR_ITEM),
        settings,
    )
    assert BAR_ITEM in {h.media_id for h in plain.hits}
    assert BAR_ITEM not in {h.media_id for h in brief.hits}


@pytest.mark.needs_postgres
async def test_an_excluded_item_cannot_come_back_through_the_lexical_retriever(session, settings):
    """The words match the bar item exactly, so only the eligible join keeps it out."""
    parsed = query.parse("bar interior nightlife, no alcohol")
    result = await fusion.search(session, parsed, helpers.unit_vector(1), settings)
    assert BAR_ITEM not in {h.media_id for h in result.hits}


@pytest.mark.needs_postgres
async def test_an_excluded_item_cannot_come_back_through_the_tag_retriever(session, settings):
    """The bar item carries the tags bar and nightlife, which tag_match scores highly."""
    parsed = query.parse("nightlife, no booze")
    result = await fusion.search(session, parsed, helpers.unit_vector(2), settings)
    assert BAR_ITEM not in {h.media_id for h in result.hits}
