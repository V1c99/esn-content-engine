"""Which probes can be trusted."""

from __future__ import annotations

# Below this the probe is shown with a warning. Two of the 23 are under it: hero at 0.797 and
# good_quality at 0.778. Both of them score how good a photo looks, which is an opinion.
WEAK_AUC = 0.85

# Probes with very few positives. Their average precision moves a lot with one label, so they
# are hints and not filters. smoking has 15 positives, food has 47, unusable has 8.
MIN_POSITIVES = 50


def is_weak(roc_auc: float) -> bool:
    return roc_auc < WEAK_AUC


def too_few_positives(n_positive: int) -> bool:
    return n_positive < MIN_POSITIVES
