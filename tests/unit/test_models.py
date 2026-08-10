"""The ORM models have to agree with what the migration built."""

from esn_engine.db.models import (
    EMBEDDING_DIMENSIONS,
    Base,
    Media,
    MediaEmbedding,
    ProbeMeta,
)


def test_every_table_the_search_needs_is_declared():
    expected = {
        "media",
        "media_embedding",
        "media_use",
        "media_avoid",
        "tag",
        "media_tag",
        "probe",
        "probe_meta",
    }
    assert set(Base.metadata.tables) == expected


def test_the_embedding_column_is_512_wide():
    """CLIP ViT-B/32 gives 512. A mismatch here only shows up when pgvector rejects a row."""
    assert EMBEDDING_DIMENSIONS == 512
    assert MediaEmbedding.__table__.c.embedding.type.dim == 512


def test_an_embedding_is_keyed_by_item_and_second():
    """Both columns, otherwise a video can only hold one vector."""
    key = {c.name for c in MediaEmbedding.__table__.primary_key.columns}
    assert key == {"media_id", "timestamp_s"}


def test_the_columns_the_exclusions_read_still_exist():
    """The venue rule is SQL over these. Renaming one turns a safety filter off."""
    for column in ("alcohol_visible", "place", "activity"):
        assert column in Media.__table__.c


def test_probe_accuracy_is_stored_next_to_the_probe_name():
    for column in ("roc_auc", "average_precision", "n_positive"):
        assert column in ProbeMeta.__table__.c


def test_deleting_an_item_takes_its_embeddings_with_it():
    fk = next(iter(MediaEmbedding.__table__.c.media_id.foreign_keys))
    assert fk.ondelete == "CASCADE"
