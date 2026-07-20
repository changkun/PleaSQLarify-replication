"""Step 3 - grouped decision variables via lift + co-occurrence (spec 06).

Implements Eq. 4/5 (lift) and Eq. 6 (co-occurrence / implicit inclusion) exactly,
and builds interpretable decision variables from functional clusters.
"""

from __future__ import annotations

from typing import Iterable

from ..model.types import (
    ActionSpace,
    Candidate,
    DecisionVariable,
    FeatureVocabulary,
    IntentSet,
)


def _contains(group: frozenset[int], cand: Candidate) -> bool:
    """g ⊆ z(a)."""
    return group <= cand.z


def lift(group: frozenset[int], members: list[Candidate], all_c: ActionSpace) -> float:
    """lift(g, C) = p_in(g) / p_all(g)  (Eq. 4, 5)."""
    if not members or not all_c:
        return 0.0
    p_in = sum(_contains(group, c) for c in members) / len(members)
    p_all = sum(_contains(group, c) for c in all_c) / len(all_c)
    if p_all == 0.0:
        return 0.0
    return p_in / p_all


def cooccurrence(
    target: frozenset[int], given: frozenset[int], all_c: ActionSpace
) -> float:
    """p(z_target = 1 | z_given = 1)  (Eq. 6).

    Probability the ``target`` atoms are present among candidates that contain the
    ``given`` atoms. With ``given`` empty this is the marginal presence rate.
    """
    denom = [c for c in all_c if _contains(given, c)]
    if not denom:
        return 0.0
    return sum(_contains(target, c) for c in denom) / len(denom)


def _candidate_groups(
    members: list[Candidate], mode: str, others: list[Candidate] | None = None
) -> list[frozenset[int]]:
    """Enumerate candidate feature groups g for a cluster (spec 06, A8a).

    ``mode``:
      * ``atomic``  - single atoms only.
      * ``grouped`` - singles + the cluster's common signature (our original A8
        gap-fill).
      * ``mined``   - singles + the cluster-characteristic itemset mined by lift
        (**the authors' rule**, see :mod:`pleasqlarify.pipeline.mining`).
    """
    atoms: set[int] = set()
    for c in members:
        atoms |= c.z
    singles = [frozenset({a}) for a in sorted(atoms)]
    if mode == "atomic":
        return singles
    if mode == "mined":
        from .mining import mine_cluster_group

        groups = list(singles)
        groups.extend(mine_cluster_group(members, others or []))
        return groups
    # grouped: singles + the cluster's common signature (intersection of members),
    # which captures jointly-emergent meaning ("interaction neglect", spec 06).
    groups = list(singles)
    if members:
        signature = frozenset.intersection(*[c.z for c in members]) if members else frozenset()
        if len(signature) > 1:
            groups.append(signature)
    return groups


def build_decision_variables(
    candidates: ActionSpace,
    intents: IntentSet,
    vocab: FeatureVocabulary,
    mode: str = "grouped",
) -> list[DecisionVariable]:
    """Build characteristic (lift > 1) decision variables over the intents.

    ``mode`` is ``"atomic"`` (single atoms), ``"grouped"`` (our cluster-signature
    gap-fill) or ``"mined"`` (the authors' lift-mined itemsets) - spec 06, A8c.
    """
    by_id = {c.id: c for c in candidates}
    reps = {cl.id: by_id[cl.representative_id] for cl in intents}

    seen_partitions: set[frozenset[int]] = set()
    variables: list[DecisionVariable] = []

    for cluster in intents:
        members = [by_id[mid] for mid in cluster.member_ids]
        member_ids = set(cluster.member_ids)
        others = [c for c in candidates if c.id not in member_ids]
        for group in _candidate_groups(members, mode, others):
            lval = lift(group, members, candidates)
            if lval <= 1.0:  # keep only characteristic groups (spec 06, A8b)
                continue
            # value_of(m): cluster m carries the group iff its representative does
            # (spec 06, A8a note: representative-based partition).
            contains = frozenset(
                cid for cid, rep in reps.items() if _contains(group, rep)
            )
            # a useful decision variable must actually split M_t
            if not contains or len(contains) == len(intents):
                continue
            if contains in seen_partitions:
                continue
            seen_partitions.add(contains)
            variables.append(
                DecisionVariable(
                    id=f"dv:{'|'.join(map(str, sorted(group)))}",
                    group=group,
                    label=vocab.label_for(group),
                    in_prob=1.0,
                    contains_cluster_ids=contains,
                )
            )
    return variables


def atom_probabilities(
    candidates: ActionSpace, selected: frozenset[int]
) -> dict[int, float]:
    """p(atom present | current selections) for every atom (spec 14 predicted query)."""
    consistent = [c for c in candidates if selected <= c.z]
    if not consistent:
        return {}
    atoms: set[int] = set()
    for c in consistent:
        atoms |= c.z
    return {
        a: sum((a in c.z) for c in consistent) / len(consistent) for a in sorted(atoms)
    }


__all__ = [
    "lift",
    "cooccurrence",
    "build_decision_variables",
    "atom_probabilities",
]
