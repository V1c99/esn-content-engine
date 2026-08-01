"""What a query can exclude, and the SQL that does it."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Exclusion:
    name: str
    # SQL that is true for an item which has to be dropped.
    predicate: str


ALCOHOL = Exclusion("alcohol", "media.alcohol_visible")

# The alcohol label only covers what was visible, so clips shot in a pub with no drink in
# frame got through. This matches the place and the activity instead.
#
# Word boundary (\y) everywhere, otherwise "public" matches pub and "barrier" matches bar.
VENUE = Exclusion(
    "alcohol-venue",
    r"""(
        media.place ~* '\y(bar|pub|cellar|tavern|brewery|nightlife|disco)\y'
        OR media.place ~* '\ybeer[- ]?(pong|garden)'
        OR (media.place ~* '\yclub\y' AND media.place !~* '\ystudent club\y')
        OR media.activity ~* '\ybeer[- ]?pong\y|\ypong table\y'
        OR (media.activity ~* '\ydrink(s|ing)?\y'
            AND media.activity !~* '\y(horse|trough)\y')
        OR EXISTS (
            SELECT 1 FROM media_tag mt
            WHERE mt.media_id = media.id
              AND mt.term = ANY(ARRAY['bar', 'pub', 'nightclub', 'nightlife',
                                      'cocktail', 'beer', 'spirit shelf', 'beer pong'])
        )
    )""",
)

# Applied whenever the query excludes anything at all. Before, one endpoint did this and the
# other did not, so the same brief gave two different answers. See docs/adr/0004.
SAFETY_FLOOR = Exclusion(
    "safety-floor",
    """EXISTS (
        SELECT 1 FROM media_avoid a
        WHERE a.media_id = media.id AND a.flag = ANY(:floor_flags)
    )""",
)

# What a user can ask to leave out, and which rules that turns into.
BY_CONCEPT: dict[str, tuple[Exclusion, ...]] = {
    "alcohol": (ALCOHOL, VENUE),
}

# Words that mean the same thing as "alcohol" in a brief.
CONCEPT_WORDS: dict[str, str] = {
    "alcohol": "alcohol",
    "alcoholic": "alcohol",
    "booze": "alcohol",
    "boozy": "alcohol",
    "drink": "alcohol",
    "drinks": "alcohol",
    "drinking": "alcohol",
    "beer": "alcohol",
    "beers": "alcohol",
    "wine": "alcohol",
    "cocktail": "alcohol",
    "cocktails": "alcohol",
    "pub": "alcohol",
    "bar": "alcohol",
    "club": "alcohol",
}
# "party" is left out of the list. It correlates with alcohol at rho 0.968 in this
# library but it is not the same thing, and "no party photos" must not start dropping clips
# for having a beer in them.
