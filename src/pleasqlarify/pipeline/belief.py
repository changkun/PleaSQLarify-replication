"""Belief distribution p_t(m) over intents (spec 07).

Supports uniform and generation-frequency initialization (spec 07, A9) and the
Eq. 3 conditioning update: keep intents consistent with the answer, renormalize.
"""

from __future__ import annotations

import math

from ..model.types import ActionSpace, Belief, DecisionVariable, IntentSet


def uniform_belief(intents: IntentSet) -> Belief:
    if not intents:
        return {}
    p = 1.0 / len(intents)
    return {cl.id: p for cl in intents}


def frequency_belief(candidates: ActionSpace, intents: IntentSet) -> Belief:
    """p_0(m) ∝ sum of gen_count over the cluster's members (spec 07, A9 alt)."""
    counts = {c.id: c.gen_count for c in candidates}
    weights = {
        cl.id: sum(counts.get(mid, 0) for mid in cl.member_ids) for cl in intents
    }
    total = sum(weights.values())
    if total == 0:
        return uniform_belief(intents)
    return {cid: w / total for cid, w in weights.items()}


def entropy(belief: Belief) -> float:
    """Shannon entropy H(p_t) in nats."""
    return -sum(p * math.log(p) for p in belief.values() if p > 0.0)


def condition(belief: Belief, variable: DecisionVariable, value: bool) -> Belief:
    """Eq. 3: restrict belief to intents with Z(m) == value, renormalize."""
    kept = {
        cid: p for cid, p in belief.items() if variable.value_of(cid) == value
    }
    total = sum(kept.values())
    if total == 0:
        return {}
    return {cid: p / total for cid, p in kept.items()}


def restrict(belief: Belief, cluster_ids: set[int]) -> Belief:
    """Renormalize belief onto a subset of surviving clusters (spec 08 recluster)."""
    kept = {cid: p for cid, p in belief.items() if cid in cluster_ids}
    total = sum(kept.values())
    if total == 0:
        return uniform_belief_from_ids(cluster_ids)
    return {cid: p / total for cid, p in kept.items()}


def uniform_belief_from_ids(cluster_ids: set[int]) -> Belief:
    if not cluster_ids:
        return {}
    p = 1.0 / len(cluster_ids)
    return {cid: p for cid in cluster_ids}


__all__ = [
    "uniform_belief",
    "frequency_belief",
    "entropy",
    "condition",
    "restrict",
    "uniform_belief_from_ids",
]
