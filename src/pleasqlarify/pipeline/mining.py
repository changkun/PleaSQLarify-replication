"""A8 aligned: frequent-itemset mining of cluster-characteristic feature groups.

The authors build the ``CLUSTER_GROUP`` condition's decision variables by mining
frequent itemsets *inside* each functional cluster and keeping the one that is most
over-represented there relative to the rest of the pool
(``run_eval.recluster_and_mine_groups`` -> ``helpers.find_best_len_for_cluster`` ->
``helpers.top_itemsets_per_cluster``). Our earlier gap-fill used each cluster's
common-atom signature (the intersection of its members), which is a much blunter
instrument: it collapses to the atoms *every* member shares, so a group that
characterises 80% of a cluster is never proposed.

Their pipeline, reproduced here:

1. For itemset length ``L = 1..max_len_max``, run apriori on the cluster's binary
   feature matrix with ``min_support_in``.
2. For each frequent itemset compute
   ``lift = supp_in / supp_pooled`` and keep those with ``lift >= min_lift``,
   sorted by ``(lift, size, supp_in)`` descending, truncated to ``top_k``.
3. Score that length by ``sum((lift - 1) * supp_in * 1/(1 + gamma*(size-1)))`` and
   keep the best-scoring ``L``.
4. Drop itemsets smaller than ``min_len`` (**2** — so mined groups are always
   multi-atom), sort by ``(lift, supp_in)``, and take the top ``top_per_cluster``
   (**1**) as that cluster's group.

``mlxtend`` is not a dependency here, so apriori is implemented directly. It is
exact, not approximate: the same downward-closure pruning, over a vocabulary
bounded by ``max_len_max <= 4``.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Optional, Sequence

from ..model.types import ActionSpace, Candidate

# The authors' parameter values (run_eval.py:988-999).
MAX_LEN_MAX = 4
MIN_SUPPORT_IN = 0.10
MIN_LIFT = 1.3
TOP_K = 12
GAMMA_SIZE_PENALTY = 0.25
MIN_LEN = 2
TOP_PER_CLUSTER = 1


@dataclass(frozen=True)
class MinedItemset:
    itemset: frozenset[int]
    size: int
    supp_in: float
    supp_out: float
    lift: float


def _support(itemset: frozenset[int], candidates: Sequence[Candidate]) -> float:
    if not candidates:
        return 0.0
    return sum(1 for c in candidates if itemset <= c.z) / len(candidates)


def apriori_itemsets(
    members: Sequence[Candidate], max_len: int, min_support: float
) -> list[frozenset[int]]:
    """Frequent itemsets up to ``max_len`` by support within ``members``.

    Downward closure: an itemset can only be frequent if all its subsets are, so
    each level is built from the previous level's survivors.
    """
    if not members or max_len < 1:
        return []
    n = len(members)
    counts: dict[int, int] = {}
    for c in members:
        for a in c.z:
            counts[a] = counts.get(a, 0) + 1
    level = [frozenset({a}) for a, k in counts.items() if k / n >= min_support]
    frequent = list(level)
    for _size in range(2, max_len + 1):
        if not level:
            break
        atoms = sorted({a for s in level for a in s})
        prev = set(level)
        nxt: list[frozenset[int]] = []
        for base in level:
            for a in atoms:
                if a in base:
                    continue
                cand = base | {a}
                if len(cand) != len(base) + 1:
                    continue
                # every (k-1)-subset must be frequent
                if any(frozenset(sub) not in prev for sub in combinations(cand, len(cand) - 1)):
                    continue
                if cand in nxt:
                    continue
                if _support(cand, members) >= min_support:
                    nxt.append(cand)
        frequent.extend(nxt)
        level = nxt
    return frequent


def top_itemsets_for_cluster(
    members: Sequence[Candidate],
    others: Sequence[Candidate],
    max_len: int,
    min_support_in: float = MIN_SUPPORT_IN,
    min_lift: float = MIN_LIFT,
    top_k: int = TOP_K,
) -> list[MinedItemset]:
    """Cluster-characteristic itemsets, ranked by lift (their `top_itemsets_per_cluster`)."""
    n_c, n_o = len(members), len(others)
    if n_c == 0:
        return []
    out: list[MinedItemset] = []
    for items in apriori_itemsets(members, max_len, min_support_in):
        supp_in = _support(items, members)
        supp_out = _support(items, others) if n_o else 0.0
        pooled = ((supp_in * n_c) + (supp_out * n_o)) / (n_c + n_o) if (n_c + n_o) else 0.0
        lift = (supp_in / pooled) if pooled > 0 else float("inf")
        if lift >= min_lift:
            out.append(MinedItemset(items, len(items), supp_in, supp_out, lift))
    out.sort(key=lambda m: (m.lift, m.size, m.supp_in), reverse=True)
    return out[:top_k]


def _score(itemsets: Sequence[MinedItemset], gamma: float) -> float:
    """sum((lift - 1) * supp_in * 1/(1 + gamma*(size-1))) — their length selector."""
    total = 0.0
    for m in itemsets:
        if m.lift == float("inf"):
            continue
        total += (m.lift - 1.0) * m.supp_in * (1.0 / (1.0 + gamma * (m.size - 1.0)))
    return total


def mine_cluster_group(
    members: Sequence[Candidate],
    others: Sequence[Candidate],
    max_len_max: int = MAX_LEN_MAX,
    min_support_in: float = MIN_SUPPORT_IN,
    min_lift: float = MIN_LIFT,
    top_k: int = TOP_K,
    gamma_size_penalty: float = GAMMA_SIZE_PENALTY,
    min_len: int = MIN_LEN,
    top_per_cluster: int = TOP_PER_CLUSTER,
) -> list[frozenset[int]]:
    """The group(s) characterising one cluster, or ``[]`` if nothing qualifies."""
    best: list[MinedItemset] = []
    best_score = float("-inf")
    for length in range(1, max_len_max + 1):
        found = top_itemsets_for_cluster(
            members, others, length, min_support_in, min_lift, top_k
        )
        score = _score(found, gamma_size_penalty) if found else float("-inf")
        if score > best_score:
            best_score, best = score, found
    # min_len = 2: mined groups are multi-atom by construction
    sized = [m for m in best if m.size >= min_len]
    if not sized:
        return []
    sized.sort(key=lambda m: (m.lift, m.supp_in), reverse=True)
    return [m.itemset for m in sized[:top_per_cluster]]


def mine_groups(
    survivors: ActionSpace, intents, max_len_max: int = MAX_LEN_MAX
) -> list[frozenset[int]]:
    """Mined groups across every functional cluster (deduplicated, order-stable)."""
    by_id = {c.id: c for c in survivors}
    seen: set[frozenset[int]] = set()
    groups: list[frozenset[int]] = []
    for cluster in intents:
        members = [by_id[m] for m in cluster.member_ids if m in by_id]
        others = [c for c in survivors if c.id not in set(cluster.member_ids)]
        for g in mine_cluster_group(members, others, max_len_max=max_len_max):
            if g not in seen:
                seen.add(g)
                groups.append(g)
    return groups


__all__ = [
    "MinedItemset",
    "apriori_itemsets",
    "top_itemsets_for_cluster",
    "mine_cluster_group",
    "mine_groups",
    "MAX_LEN_MAX",
    "MIN_SUPPORT_IN",
    "MIN_LIFT",
    "TOP_K",
    "GAMMA_SIZE_PENALTY",
    "MIN_LEN",
]
