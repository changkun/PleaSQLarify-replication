"""Per-turn evaluation metrics + bootstrap CIs (spec 10).

* gold-label entropy: Shannon entropy of the survivor->gold-intent distribution
  (count-based q_t, so it is comparable across all five conditions; A15).
* functional output similarity: mean pairwise S among surviving candidates.
"""

from __future__ import annotations

import math
from collections import Counter

import numpy as np


def gold_label_entropy(surviving_ids: list[str], gold_assignment: dict[str, int]) -> float:
    """H(q_t): residual semantic uncertainty over gold intents (spec 10)."""
    if not surviving_ids:
        return 0.0
    counts = Counter(gold_assignment[cid] for cid in surviving_ids if cid in gold_assignment)
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return -sum((n / total) * math.log(n / total) for n in counts.values())


def mean_pairwise_similarity(indices: list[int], sim: np.ndarray) -> float:
    """Mean off-diagonal functional similarity among surviving candidates (spec 10)."""
    if len(indices) <= 1:
        return 1.0  # a single functional survivor is trivially homogeneous
    sub = sim[np.ix_(indices, indices)]
    n = len(indices)
    off = (sub.sum() - np.trace(sub)) / (n * (n - 1))
    return float(off)


def bootstrap_ci(
    values: list[float], n_boot: int = 10000, ci: float = 0.95, seed: int = 0
) -> tuple[float, float, float]:
    """Return (median, lo, hi) with a percentile bootstrap CI over the median."""
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return (float("nan"), float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    boot_medians = np.empty(n_boot)
    for b in range(n_boot):
        sample = rng.choice(arr, size=arr.size, replace=True)
        boot_medians[b] = np.median(sample)
    alpha = (1.0 - ci) / 2.0
    lo = float(np.quantile(boot_medians, alpha))
    hi = float(np.quantile(boot_medians, 1.0 - alpha))
    return (float(np.median(arr)), lo, hi)


__all__ = ["gold_label_entropy", "mean_pairwise_similarity", "bootstrap_ci"]
