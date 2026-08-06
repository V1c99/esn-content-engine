"""Copy the old SQLite library into Postgres.

Usage:  python scripts/import_library.py path/to/library.db

The old engine kept everything in one SQLite file. This reads it and fills the Postgres
tables. Safe to run again, it clears the tables first.
"""

from __future__ import annotations

import asyncio
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

import asyncpg
import numpy as np
from pgvector.asyncpg import register_vector

from esn_engine.core.config import get_settings

# Order matters, the foreign keys point at media.
TABLES = [
    "probe_meta",
    "probe",
    "media_tag",
    "tag",
    "media_avoid",
    "media_use",
    "media_embedding",
    "media",
]


def dsn() -> str:
    # asyncpg does not understand the SQLAlchemy prefix.
    return get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://")


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=UTC)
    except ValueError:
        return None


def vector_of(blob: bytes | None) -> np.ndarray | None:
    if not blob:
        return None
    v = np.frombuffer(blob, dtype=np.float32)
    # Everything in the old library is already unit length, but a couple of rows were written
    # before that was true, so normalise again.
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else None


async def main(sqlite_path: Path) -> None:
    old = sqlite3.connect(sqlite_path)
    old.row_factory = sqlite3.Row
    pg = await asyncpg.connect(dsn())
    await register_vector(pg)

    try:
        await pg.execute("TRUNCATE " + ", ".join(TABLES) + " CASCADE")

        media = []
        for r in old.execute("SELECT * FROM items"):
            media.append(
                (
                    r["id"],
                    r["path"],
                    r["name"],
                    r["event"],
                    r["kind"],
                    r["w"],
                    r["h"],
                    r["dur"],
                    parse_date(r["date"]),
                    r["bytes"],
                    r["ai_desc"] or r["description"],
                    r["ai_place"],
                    r["ai_act"],
                    r["ai_inout"],
                    r["ai_time"],
                    r["ai_people"],
                    r["ai_emotion"],
                    bool(r["ai_alcohol"]),
                )
            )
        await pg.copy_records_to_table(
            "media",
            records=media,
            columns=[
                "id",
                "path",
                "name",
                "event",
                "kind",
                "width",
                "height",
                "duration_s",
                "shot_at",
                "bytes",
                "description",
                "place",
                "activity",
                "indoor_outdoor",
                "time_of_day",
                "people_count",
                "emotion",
                "alcohol_visible",
            ],
        )
        print(f"media                {len(media):>7}")

        # One embedding per item at t=0, then one per sampled video frame at its own second.
        embeddings = []
        for r in old.execute("SELECT id, emb FROM items WHERE emb IS NOT NULL"):
            v = vector_of(r["emb"])
            if v is not None:
                embeddings.append((r["id"], 0.0, v))
        whole = len(embeddings)

        seen = {(m, 0.0) for m, _, _ in embeddings}
        for r in old.execute("SELECT item_id, t, emb FROM vframes WHERE emb IS NOT NULL"):
            key = (r["item_id"], float(r["t"]))
            # A frame sampled at second 0 collides with the whole-item row.
            if key in seen:
                continue
            v = vector_of(r["emb"])
            if v is not None:
                seen.add(key)
                embeddings.append((r["item_id"], float(r["t"]), v))
        await pg.copy_records_to_table(
            "media_embedding",
            records=embeddings,
            columns=["media_id", "timestamp_s", "embedding"],
        )
        print(
            f"media_embedding      {len(embeddings):>7}  ({whole} whole, "
            f"{len(embeddings) - whole} frames)"
        )

        uses = [(r["item_id"], r["use"]) for r in old.execute("SELECT item_id, use FROM ai_use")]
        await pg.executemany(
            "INSERT INTO media_use (media_id, use) VALUES ($1, $2) ON CONFLICT DO NOTHING", uses
        )
        print(f"media_use            {len(uses):>7}")

        avoid = [
            (r["item_id"], r["flag"]) for r in old.execute("SELECT item_id, flag FROM ai_avoid")
        ]
        await pg.executemany(
            "INSERT INTO media_avoid (media_id, flag) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            avoid,
        )
        print(f"media_avoid          {len(avoid):>7}")

        # Document counts are computed here rather than copied from the old vocab table, so
        # they always match the rows that actually got imported.
        rows = list(
            old.execute(
                "SELECT item_id, tag, src, w FROM ai_tags WHERE tag IS NOT NULL AND tag <> ''"
            )
        )
        counts: dict[str, set[int]] = {}
        for r in rows:
            counts.setdefault(r["tag"].strip().lower(), set()).add(r["item_id"])
        await pg.copy_records_to_table(
            "tag",
            records=[(term, len(ids)) for term, ids in counts.items()],
            columns=["term", "document_count"],
        )
        print(f"tag                  {len(counts):>7}")

        media_tags = {}
        for r in rows:
            key = (r["item_id"], r["tag"].strip().lower(), r["src"] or "vision")
            # Keep the highest weight if the same tag arrives twice from one source.
            media_tags[key] = max(media_tags.get(key, 0.0), float(r["w"] or 1.0))
        await pg.copy_records_to_table(
            "media_tag",
            records=[(m, t, s, w) for (m, t, s), w in media_tags.items()],
            columns=["media_id", "term", "source", "weight"],
        )
        print(f"media_tag            {len(media_tags):>7}")

        probes = {}
        for r in old.execute("SELECT item_id, name, p FROM probe"):
            probes[(r["item_id"], r["name"])] = float(r["p"])
        await pg.copy_records_to_table(
            "probe",
            records=[(m, n, p) for (m, n), p in probes.items()],
            columns=["media_id", "name", "p"],
        )
        meta = [
            (r["name"], float(r["auc"]), float(r["ap"]), int(r["n_pos"]))
            for r in old.execute("SELECT name, auc, ap, n_pos FROM probe_meta")
        ]
        await pg.copy_records_to_table(
            "probe_meta",
            records=meta,
            columns=["name", "roc_auc", "average_precision", "n_positive"],
        )
        print(f"probe                {len(probes):>7}")
        print(f"probe_meta           {len(meta):>7}")

        # Name and event get weight B, the description and the tags get A, so a word in the
        # description ranks above the same word in a file name.
        await pg.execute("""
            UPDATE media SET search_vector =
                setweight(to_tsvector('english',
                    coalesce(name, '') || ' ' || coalesce(event, '')), 'B')
                ||
                setweight(to_tsvector('english',
                    coalesce(description, '') || ' ' || coalesce(
                        (SELECT string_agg(term, ' ') FROM media_tag WHERE media_id = media.id),
                        '')), 'A')
        """)
        print("search_vector        built")
    finally:
        await pg.close()
        old.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    asyncio.run(main(Path(sys.argv[1])))
