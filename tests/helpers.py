"""A small library to test against, built to contain the cases that went wrong before."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

DIMENSIONS = 512


def unit_vector(seed: int) -> list[float]:
    """A repeatable random unit vector. The numbers do not matter, only that they are stable."""
    rng = np.random.default_rng(seed)
    v = rng.normal(size=DIMENSIONS)
    v = v / np.linalg.norm(v)
    return [float(x) for x in v]


def as_pgvector(values: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in values) + "]"


@dataclass
class Item:
    id: int
    name: str
    kind: str = "photo"
    event: str | None = "test_event"
    description: str | None = None
    place: str | None = None
    activity: str | None = None
    alcohol_visible: bool = False
    tags: tuple[str, ...] = ()
    avoid: tuple[str, ...] = ()
    uses: tuple[str, ...] = ()
    # Extra video frames, as seconds. The whole item always gets one at 0.
    frames: tuple[float, ...] = ()
    vector_seed: int | None = None
    duration_s: float | None = None
    extra_vectors: dict[float, int] = field(default_factory=dict)


# The traps. Each of these broke something in the old engine, so they all have a test.
LIBRARY: tuple[Item, ...] = (
    Item(
        1,
        "public_square.jpg",
        place="public square",
        activity="walking around",
        description="volunteers in a public square",
        tags=("square", "walking"),
    ),
    Item(
        2,
        "beginning_of_hike.jpg",
        place="mountain trail",
        activity="beginning the hike",
        description="the beginning of a hike",
        tags=("hiking", "mountain"),
    ),
    Item(
        3,
        "crowd_barrier.jpg",
        place="concert barrier",
        activity="standing at the barrier",
        description="a crowd barrier at a concert",
        tags=("concert", "crowd"),
    ),
    Item(
        4,
        "student_club.jpg",
        place="student club room",
        activity="board meeting",
        description="volunteers in the student club room",
        tags=("meeting", "students"),
    ),
    Item(
        5,
        "horse_trough.jpg",
        place="mountain meadow",
        activity="horse drinking at a trough",
        description="a horse drinking water",
        tags=("horse", "animals"),
    ),
    Item(
        6,
        "wide_shot_hall.jpg",
        place="sports hall",
        activity="wide shots of the game",
        description="wide camera shots of a basketball game",
        tags=("basketball", "sport"),
    ),
    Item(
        7,
        "bar_interior.jpg",
        place="bar interior",
        activity="socialising",
        description="inside a bar",
        tags=("bar", "nightlife"),
    ),
    Item(
        8,
        "beer_on_table.jpg",
        place="party marquee tent",
        activity="drinking beer",
        alcohol_visible=True,
        description="beers on a table",
        tags=("beer", "party"),
    ),
    Item(
        9,
        "face_down_street.jpg",
        place="old town street",
        activity="lying in the street",
        avoid=("reputational",),
        description="somebody lying in the street at night",
        tags=("street", "night"),
    ),
    Item(
        10,
        "recruitment_hero.jpg",
        place="university courtyard",
        activity="posing for a photo",
        uses=("recruitment", "hero"),
        description="happy volunteers posing",
        tags=("volunteers", "posing"),
    ),
    Item(
        11,
        "paws_dog.jpg",
        place="animal shelter",
        activity="petting a dog",
        description="a volunteer petting a dog",
        tags=("dog", "animals", "shelter"),
    ),
    # A long video. Every one of its frames is close to the query vector, which is what used
    # to fill the whole result page.
    Item(
        12,
        "long_clip.mp4",
        kind="video",
        duration_s=60.0,
        place="university courtyard",
        activity="walking around",
        description="a long clip of the courtyard",
        tags=("courtyard",),
        frames=tuple(float(t) for t in range(1, 40)),
        extra_vectors={41.0: 99},
    ),
)


async def seed(session: AsyncSession) -> None:
    """Put the test library into an empty database."""
    for item in LIBRARY:
        await session.execute(
            text("""
                INSERT INTO media (id, path, name, event, kind, duration_s, description,
                                   place, activity, alcohol_visible)
                VALUES (:id, :path, :name, :event, :kind, :duration_s, :description,
                        :place, :activity, :alcohol_visible)
            """),
            {
                "id": item.id,
                "path": f"/media/{item.name}",
                "name": item.name,
                "event": item.event,
                "kind": item.kind,
                "duration_s": item.duration_s,
                "description": item.description,
                "place": item.place,
                "activity": item.activity,
                "alcohol_visible": item.alcohol_visible,
            },
        )

        seed_value = item.vector_seed if item.vector_seed is not None else item.id
        await _add_vector(session, item.id, 0.0, seed_value)
        for t in item.frames:
            # All the frames of the long clip share the base seed, so they sit on top of each
            # other and one clip can try to fill the whole page.
            await _add_vector(session, item.id, t, seed_value)
        for t, other_seed in item.extra_vectors.items():
            await _add_vector(session, item.id, t, other_seed)

        for term in item.tags:
            await session.execute(
                text("""INSERT INTO media_tag (media_id, term, source, weight)
                        VALUES (:id, :term, 'vision', 1.0)"""),
                {"id": item.id, "term": term},
            )
        for flag in item.avoid:
            await session.execute(
                text("INSERT INTO media_avoid (media_id, flag) VALUES (:id, :flag)"),
                {"id": item.id, "flag": flag},
            )
        for use in item.uses:
            await session.execute(
                text("INSERT INTO media_use (media_id, use) VALUES (:id, :use)"),
                {"id": item.id, "use": use},
            )

    # document_count drives the IDF weight, so it has to match the rows above.
    await session.execute(
        text("""INSERT INTO tag (term, document_count)
                SELECT term, count(DISTINCT media_id) FROM media_tag GROUP BY term""")
    )
    await session.execute(
        text("""
            UPDATE media SET search_vector =
                setweight(to_tsvector('english',
                    coalesce(name, '') || ' ' || coalesce(event, '')), 'B')
                ||
                setweight(to_tsvector('english',
                    coalesce(description, '') || ' ' || coalesce(
                        (SELECT string_agg(term, ' ') FROM media_tag
                         WHERE media_id = media.id), '')), 'A')
        """)
    )
    await session.execute(
        text("""INSERT INTO probe_meta (name, roc_auc, average_precision, n_positive) VALUES
                ('alcohol', 0.985, 0.952, 526),
                ('animals', 0.999, 0.993, 251),
                ('hero', 0.797, 0.518, 527),
                ('good_quality', 0.778, 0.786, 1260),
                ('smoking', 0.989, 0.620, 15)""")
    )
    await session.execute(
        text("""INSERT INTO probe (media_id, name, p) VALUES
                (11, 'animals', 0.97), (11, 'hero', 0.44), (8, 'alcohol', 0.99)""")
    )
    await session.commit()


async def _add_vector(session: AsyncSession, media_id: int, t: float, seed_value: int) -> None:
    await session.execute(
        text("""INSERT INTO media_embedding (media_id, timestamp_s, embedding)
                VALUES (:id, :t, CAST(:v AS vector))"""),
        {"id": media_id, "t": t, "v": as_pgvector(unit_vector(seed_value))},
    )
