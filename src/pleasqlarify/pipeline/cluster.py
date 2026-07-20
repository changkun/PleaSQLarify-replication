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


LINKAGES = ("average", "complete", "single")

# The authors' live k rule (their run_eval.recluster_and_mine_groups), which
# shadows the silhouette-based helper that never runs. k is a size heuristic on
# the number of *surviving* candidates, recomputed every turn (A5).
TARGET_CLUSTER_SIZE = 10
MAX_K = 4
MIN_K = 2


def authors_k(n_survivors: int, target_cluster_size: int = TARGET_CLUSTER_SIZE,
              max_k: int = MAX_K) -> int:
    """k = max(2, min(max_K, round(n / target_cluster_size) or 2)) — verbatim (A5)."""
    return max(MIN_K, min(max_k, int(round(n_survivors / target_cluster_size)) or MIN_K))


def _agglomerate_scipy(
    dist: np.ndarray, k: int | None, threshold: float, linkage: str
) -> list[list[int]] | None:
    """SciPy-backed agglomeration — the authors' path, and O(n^2) rather than O(n^3).

    Their ``hierarchical_clusters_from_similarity`` uses
    ``scipy.cluster.hierarchy.linkage(squareform(1 - S), method=...)`` and cuts with
    ``fcluster``. Our pure-numpy fallback below is equivalent for the linkages we
    expose but is far too slow for their ~95-candidate pools re-clustered each turn.

    Returns ``None`` if SciPy is unavailable, so the caller can fall back.
    """
    try:
        from scipy.cluster.hierarchy import fcluster, linkage as scipy_linkage
        from scipy.spatial.distance import squareform
    except ImportError:  # pragma: no cover - scipy ships with the real stack
        return None

    n = dist.shape[0]
    if n < 2:
        return [[i] for i in range(n)]
    sym = (dist + dist.T) / 2.0
    np.fill_diagonal(sym, 0.0)
    np.clip(sym, 0.0, None, out=sym)
    Z = scipy_linkage(squareform(sym, checks=False), method=linkage)
    if k is not None:
        labels = fcluster(Z, t=max(1, min(int(k), n)), criterion="maxclust")
    else:
        labels = fcluster(Z, t=threshold, criterion="distance")
    groups: dict[int, list[int]] = {}
    for idx, lab in enumerate(labels):
        groups.setdefault(int(lab), []).append(idx)
    return sorted(groups.values(), key=min)


def _agglomerate(
    dist: np.ndarray, k: int | None, threshold: float, linkage: str = "average"
) -> list[list[int]]:
    if linkage not in LINKAGES:
        raise ValueError(f"unknown linkage: {linkage!r}")
    n = dist.shape[0]
    if n == 0:
        return []
    fast = _agglomerate_scipy(dist, k, threshold, linkage)
    if fast is not None:
        return fast
    clusters: list[list[int]] = [[i] for i in range(n)]

    if linkage == "average":
        combine = np.mean
    elif linkage == "complete":
        combine = np.max      # merges only when *every* pair is close: resists over-merging
    elif linkage == "single":
        combine = np.min      # chains through any one close pair: merges most eagerly
    else:
        raise ValueError(f"unknown linkage: {linkage!r}")

    def cluster_distance(a: list[int], b: list[int]) -> float:
        return float(combine([dist[i, j] for i in a for j in b]))

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
    linkage: str = "average",
) -> IntentSet:
    """Cluster candidates by output similarity; sets ``candidate.cluster_id``."""
    dist = 1.0 - sim
    np.fill_diagonal(dist, 0.0)
    groups = _agglomerate(dist, k=k, threshold=threshold, linkage=linkage)

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


__all__ = ["cluster_candidates", "LINKAGES", "authors_k", "TARGET_CLUSTER_SIZE", "MAX_K"]
