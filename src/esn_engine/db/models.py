"""The tables."""

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# CLIP ViT-B/32 gives 512 numbers per image or per text.
EMBEDDING_DIMENSIONS = 512


class Base(DeclarativeBase):
    pass


class Media(Base):
    """One photo or one video."""

    __tablename__ = "media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    event: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text, nullable=False)

    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_s: Mapped[float | None] = mapped_column(Float)
    shot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bytes: Mapped[int | None] = mapped_column(BigInteger)

    # These come from the vision labelling pass over the library.
    description: Mapped[str | None] = mapped_column(Text)
    place: Mapped[str | None] = mapped_column(Text)
    activity: Mapped[str | None] = mapped_column(Text)
    indoor_outdoor: Mapped[str | None] = mapped_column(Text)
    time_of_day: Mapped[str | None] = mapped_column(Text)
    people_count: Mapped[str | None] = mapped_column(Text)
    emotion: Mapped[str | None] = mapped_column(Text)

    # Careful with this one. The exclusion filters are SQL over alcohol_visible, place and
    # activity, so renaming a column here turns a safety filter off and nothing crashes.
    # The probe table is not used for exclusions.
    alcohol_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    search_vector: Mapped[str | None] = mapped_column(TSVECTOR)


class MediaEmbedding(Base):
    """A vector for a whole item, or for one second of a video.

    Photos and whole videos are stored at timestamp_s = 0, video frames at the second they
    were sampled from. That is why the timestamp is part of the primary key: it lets a search
    return the moment inside a clip and not only the clip.
    """

    __tablename__ = "media_embedding"

    media_id: Mapped[int] = mapped_column(
        ForeignKey("media.id", ondelete="CASCADE"), primary_key=True
    )
    timestamp_s: Mapped[float] = mapped_column(Float, primary_key=True, default=0.0)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=False)


class MediaUse(Base):
    """What a clip is good for: recruitment, opener, hero and so on."""

    __tablename__ = "media_use"
    __table_args__ = (UniqueConstraint("media_id", "use", name="uq_media_use"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    media_id: Mapped[int] = mapped_column(ForeignKey("media.id", ondelete="CASCADE"), index=True)
    use: Mapped[str] = mapped_column(Text, nullable=False)


class MediaAvoid(Base):
    """Reasons not to use a clip. The safety floor reads `reputational` from here."""

    __tablename__ = "media_avoid"
    __table_args__ = (UniqueConstraint("media_id", "flag", name="uq_media_avoid"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    media_id: Mapped[int] = mapped_column(ForeignKey("media.id", ondelete="CASCADE"), index=True)
    flag: Mapped[str] = mapped_column(Text, nullable=False)


class Tag(Base):
    __tablename__ = "tag"

    term: Mapped[str] = mapped_column(Text, primary_key=True)
    # How many items have this tag. Needed for the IDF weight in tag_match().
    document_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class MediaTag(Base):
    __tablename__ = "media_tag"
    __table_args__ = (UniqueConstraint("media_id", "term", "source", name="uq_media_tag"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    media_id: Mapped[int] = mapped_column(ForeignKey("media.id", ondelete="CASCADE"), index=True)
    term: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="vision")
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)


class Probe(Base):
    """One probe score for one item, as a probability between 0 and 1."""

    __tablename__ = "probe"
    __table_args__ = (UniqueConstraint("media_id", "name", name="uq_probe"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    media_id: Mapped[int] = mapped_column(ForeignKey("media.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    p: Mapped[float] = mapped_column(Float, nullable=False)


class ProbeMeta(Base):
    """Cross-validated accuracy for each probe.

    Kept in the database next to the scores because a probe with AUC 0.78 and one with 0.99
    look the same in the probe table, and the weak ones have to be shown with a warning.
    """

    __tablename__ = "probe_meta"

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    roc_auc: Mapped[float] = mapped_column(Float, nullable=False)
    average_precision: Mapped[float] = mapped_column(Float, nullable=False)
    n_positive: Mapped[int] = mapped_column(Integer, nullable=False)
