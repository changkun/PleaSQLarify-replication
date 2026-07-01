"""Step 2 (part 2) - functional clustering into intents M (spec 04).

Deterministic agglomerative (average-linkage) clustering on the output distance
``D = 1 - S``. We implement it in pure numpy (N <= 50) rather than pulling in
scipy/sklearn, keeping the core dependency-light and the determinism explicit
(the paper chose hierarchical clustering precisely because it is deterministic and
lets you fix the number of clusters, p. 7).

Two modes (spec 04, A5):
* threshold mode (interactive tool): merge while the linkage distance is below
  ``threshold`` (i.e. outputs with cosine >= 1 - threshold), so k is data-driven.
* fixed-k mode (benchmark): keep merging until exactly ``k`` clusters remain.
"""

from __future__ import annotations

from itertools import combinations

import numpy as np

from ..model.types import Candidate, Cluster, IntentSet


def _agglomerate(
    dist: np.ndarray, k: int | None, threshold: float
) -> list[list[int]]:
    n = dist.shape[0]
    if n == 0:
        return []
    clusters: list[list[int]] = [[i] for i in range(n)]

    def cluster_distance(a: list[int], b: list[int]) -> float:
        return float(np.mean([dist[i, j] for i in a for j in b]))

    target = k if k is not None else 1
    while len(clusters) > target:
        best_pair: tuple[int, int] | None = None
        best_d = float("inf")
        for x, y in combinations(range(len(clusters)), 2):
            d = cluster_distance(clusters[x], clusters[y])
            if d < best_d - 1e-12:
                best_d = d
                best_pair = (x, y)
        if best_pair is None:
            break
        if k is None and best_d > threshold:
            break
        x, y = best_pair
        clusters[x] = clusters[x] + clusters[y]
        del clusters[y]

    # deterministic order: sort clusters by their smallest member index
    clusters.sort(key=min)
    return clusters


def cluster_candidates(
    candidates: list[Candidate],
    sim: np.ndarray,
    k: int | None = None,
    threshold: float = 0.1,
) -> IntentSet:
    """Cluster candidates by output similarity; sets ``candidate.cluster_id``."""
    dist = 1.0 - sim
    np.fill_diagonal(dist, 0.0)
    groups = _agglomerate(dist, k=k, threshold=threshold)

    intents: IntentSet = []
    for cid, members in enumerate(groups):
        member_cands = [candidates[i] for i in members]
        for c in member_cands:
            c.cluster_id = cid
        # representative = most-probable (highest gen_count), tie -> lowest id
        rep = sorted(member_cands, key=lambda c: (-c.gen_count, c.id))[0]
        intents.append(
            Cluster(id=cid, member_ids=[c.id for c in member_cands], representative_id=rep.id)
        )
    return intents


__all__ = ["cluster_candidates"]
