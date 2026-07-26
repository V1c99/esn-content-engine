"""Media library, embeddings and the tag scorer.

Revision ID: 0001_media_library
Revises:
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001_media_library"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# m = neighbours per node, ef_construction = candidate list size while building. Left at the
# pgvector defaults. Recall came out 0.99 against the old exhaustive scan, good enough.
HNSW_INDEX = """
CREATE INDEX idx_media_embedding_hnsw
ON media_embedding USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64)
"""

# The tag retriever. Sums the IDF of the tags that matched, so a rare tag counts more than a
# tag half the library has.
#
# The two GREATEST calls are there because it divided by zero the first time, when a term was
# in the vocab with document_count 0.
TAG_MATCH = """
CREATE FUNCTION tag_match(q text)
RETURNS TABLE (media_id integer, idf_weighted_score double precision)
LANGUAGE sql
STABLE
AS $$
    WITH corpus AS (
        SELECT GREATEST(count(*), 1)::double precision AS n FROM media
    ),
    terms AS (
        SELECT DISTINCT unnest(regexp_split_to_array(lower(q), '[^a-z0-9]+')) AS term
    ),
    weighted AS (
        SELECT terms.term,
               ln(corpus.n / GREATEST(tag.document_count, 1)::double precision) AS idf
        FROM terms
        JOIN tag ON tag.term = terms.term
        CROSS JOIN corpus
        WHERE terms.term <> ''
    )
    SELECT media_tag.media_id,
           sum(weighted.idf * media_tag.weight) AS idf_weighted_score
    FROM media_tag
    JOIN weighted ON weighted.term = media_tag.term
    GROUP BY media_tag.media_id
$$
"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "media",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("event", sa.Text()),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("duration_s", sa.Float()),
        sa.Column("shot_at", sa.DateTime(timezone=True)),
        sa.Column("bytes", sa.BigInteger()),
        sa.Column("description", sa.Text()),
        sa.Column("place", sa.Text()),
        sa.Column("activity", sa.Text()),
        sa.Column("indoor_outdoor", sa.Text()),
        sa.Column("time_of_day", sa.Text()),
        sa.Column("people_count", sa.Text()),
        sa.Column("emotion", sa.Text()),
        sa.Column("alcohol_visible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("search_vector", postgresql.TSVECTOR()),
        sa.UniqueConstraint("path", name="uq_media_path"),
    )
    op.create_index("ix_media_kind", "media", ["kind"])
    op.create_index("ix_media_event", "media", ["event"])
    # GIN index, otherwise the tsvector search does a full scan.
    op.execute("CREATE INDEX ix_media_search_vector ON media USING gin (search_vector)")

    op.create_table(
        "media_embedding",
        sa.Column("media_id", sa.Integer(), nullable=False),
        sa.Column("timestamp_s", sa.Float(), nullable=False, server_default="0"),
        sa.Column("embedding", Vector(512), nullable=False),
        sa.ForeignKeyConstraint(["media_id"], ["media.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("media_id", "timestamp_s"),
    )
    op.execute(HNSW_INDEX)

    op.create_table(
        "media_use",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("media_id", sa.Integer(), nullable=False),
        sa.Column("use", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["media_id"], ["media.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("media_id", "use", name="uq_media_use"),
    )
    op.create_index("ix_media_use_media_id", "media_use", ["media_id"])
    op.create_index("ix_media_use_use", "media_use", ["use"])

    op.create_table(
        "media_avoid",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("media_id", sa.Integer(), nullable=False),
        sa.Column("flag", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["media_id"], ["media.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("media_id", "flag", name="uq_media_avoid"),
    )
    op.create_index("ix_media_avoid_media_id", "media_avoid", ["media_id"])
    op.create_index("ix_media_avoid_flag", "media_avoid", ["flag"])

    op.create_table(
        "tag",
        sa.Column("term", sa.Text(), primary_key=True),
        sa.Column("document_count", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "media_tag",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("media_id", sa.Integer(), nullable=False),
        sa.Column("term", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False, server_default="vision"),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.ForeignKeyConstraint(["media_id"], ["media.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("media_id", "term", "source", name="uq_media_tag"),
    )
    op.create_index("ix_media_tag_media_id", "media_tag", ["media_id"])
    op.create_index("ix_media_tag_term", "media_tag", ["term"])

    op.create_table(
        "probe",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("media_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("p", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["media_id"], ["media.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("media_id", "name", name="uq_probe"),
    )
    op.create_index("ix_probe_media_id", "probe", ["media_id"])
    op.create_index("ix_probe_name", "probe", ["name"])

    op.create_table(
        "probe_meta",
        sa.Column("name", sa.Text(), primary_key=True),
        sa.Column("roc_auc", sa.Float(), nullable=False),
        sa.Column("average_precision", sa.Float(), nullable=False),
        sa.Column("n_positive", sa.Integer(), nullable=False),
    )

    op.execute(TAG_MATCH)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS tag_match(text)")
    op.drop_table("probe_meta")
    op.drop_table("probe")
    op.drop_table("media_tag")
    op.drop_table("tag")
    op.drop_table("media_avoid")
    op.drop_table("media_use")
    op.drop_table("media_embedding")
    op.drop_table("media")
