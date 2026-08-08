"""A probe that is not accurate has to say so wherever it appears."""

import pytest
from sqlalchemy import text

from esn_engine.probes.quality import WEAK_AUC, is_weak, too_few_positives

pytestmark = pytest.mark.contract


def test_the_two_weak_probes_are_marked_weak():
    """hero is 0.797 and good_quality is 0.778, so neither is worth filtering on."""
    assert is_weak(0.797)
    assert is_weak(0.778)
    assert not is_weak(0.985)


def test_a_probe_with_too_few_positives_is_flagged():
    """smoking has 15 positives and unusable has 8. Their AP moves with one label."""
    assert too_few_positives(15)
    assert too_few_positives(8)
    assert not too_few_positives(526)


@pytest.mark.needs_postgres
async def test_every_probe_carries_the_accuracy_it_was_measured_at(session):
    """A score with no accuracy next to it looks the same whether the probe works or not."""
    rows = await session.execute(
        text("""SELECT p.name FROM probe p
                LEFT JOIN probe_meta m ON m.name = p.name
                WHERE m.name IS NULL""")
    )
    orphans = [r.name for r in rows]
    assert orphans == [], f"probes with no measured accuracy: {orphans}"


@pytest.mark.needs_postgres
async def test_the_weak_threshold_matches_what_the_database_reports(session):
    rows = await session.execute(text("SELECT name, roc_auc FROM probe_meta ORDER BY roc_auc"))
    for row in rows:
        assert is_weak(row.roc_auc) == (row.roc_auc < WEAK_AUC)
