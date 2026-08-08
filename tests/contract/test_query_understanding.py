"""What the parser has to get right. A missed negation puts the clips straight back in."""

import pytest

from esn_engine.search import query
from esn_engine.search.query import NEGATIONS

pytestmark = pytest.mark.contract


def test_no_booze_excludes_alcohol():
    parsed = query.parse("happy volunteers, no booze")
    assert parsed.excluded == ("alcohol",)
    assert "booze" not in parsed.text


@pytest.mark.parametrize("word", sorted(NEGATIONS))
def test_every_negation_word_triggers_the_exclusion(word):
    """All of them have to work. Adding a word to the set and forgetting the mapping leaks."""
    parsed = query.parse(f"volunteers {word} alcohol")
    assert parsed.excluded == ("alcohol",), f"{word!r} did not negate"


def test_a_negation_word_never_reaches_the_search_text():
    """The word no used to end up in the tsquery, which matched nothing at all."""
    parsed = query.parse("street at night, no alcohol")
    for word in ("no", "alcohol"):
        assert word not in parsed.text.split()


def test_filler_words_are_dropped():
    parsed = query.parse("show me some of the volunteers")
    assert parsed.text == "volunteers"


def test_clips_means_video_and_photos_means_photo():
    assert query.parse("clips of the hike").kind == "video"
    assert query.parse("photos of the hike").kind == "photo"


def test_asking_for_both_photos_and_videos_does_not_filter_kind():
    assert query.parse("photos and videos from the hike").kind is None


def test_a_query_of_only_filler_still_searches_something():
    """Stripping every word left an empty tsquery, which returned the whole library."""
    parsed = query.parse("show me some stuff")
    assert parsed.text.strip() != ""


def test_party_is_not_treated_as_alcohol():
    """They correlate at rho 0.968 in the library but they are not the same thing."""
    parsed = query.parse("volunteers, no party")
    assert parsed.excluded == ()
