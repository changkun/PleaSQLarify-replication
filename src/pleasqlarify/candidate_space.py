"""A10 aligned: decision variables over **candidates**, not over cluster partitions.

Our original architecture (spec 07, A10) treats one functional cluster as one
intent, puts the belief over clusters, and makes a decision variable a *partition
of clusters*. The authors' code is candidate-level throughout:

* ``CandidateSQL.prob`` is the **generation frequency** of that query
  (``build_normalized_feature_matrix`` -> ``normalized_count``), so the belief is
  over candidates.
* ``DecisionVar.cand_indices_by_val`` maps each value to the **candidate indices**
  in that branch (``build_group_decision_vars``, ``find_decision_vars``).
* ``eig(var, cands) = H(probs) - Σ_v P(v)·H(probs | v)`` is computed over those
  candidate probabilities.

Clustering enters only in *which* variables exist — the mined itemsets — not in
the belief or the information gain.

This matters because it is the reason our Feature Grouping condition was inert: a
mined group and a single atom can induce the same *cluster* partition while
splitting the *candidates* differently. Under this module they are distinct
variables, as they are for the authors.

Our :func:`pleasqlarify.pipeline.ranking.information_gain` is generic over the
belief's keys, so with candidate-indexed belief it computes their ``eig`` exactly;
nothing about the IG formula changes.

The two group split modes they implement map onto their two clustering conditions:

* ``group_split="mask"`` (their default) — branch 1 is the candidates satisfying
  the itemset conjunction → ``CLUSTER_GROUP``.
* ``group_split="cluster"`` — branch 1 is the mined cluster's members →
  ``CLUSTER_CHARACTERISTIC``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .eval.metrics import mean_pairwise_similarity
from .model.types import (
    ActionSpace,
    Belief,
    Candidate,
    DecisionVariable,
    FeatureVocabulary,
    IntentSet,
)
from .pipeline.cluster import authors_k, cluster_candidates
from .pipeline.mining import mine_cluster_group
from .pipeline.ranking import rank_variables
from .pipeline.repair_loop import SIM_STOP_TOL

MIN_BIN_FRAC = 0.02  # their build_group_decision_vars default


def frequency_prior(survivors: ActionSpace, index_of: dict[str, int]) -> Belief:
    """p(candidate) ∝ gen_count — their normalized generation frequency."""
    total = sum(max(c.gen_count, 1) for c in survivors)
    if total <= 0:
        return {}
    return {index_of[c.id]: max(c.gen_count, 1) / total for c in survivors}


def _variable(
    group: frozenset[int], label: str, positives: frozenset[int], name: str
) -> DecisionVariable:
    # `contains_cluster_ids` carries candidate indices here; `value_of` is unchanged.
    return DecisionVariable(
        id=name, group=group, label=label, contains_cluster_ids=positives
    )


def build_candidate_variables(
    survivors: ActionSpace,
    intents: IntentSet,
    vocab: FeatureVocabulary,
    index_of: dict[str, int],
    belief: Belief,
    include_atomic: bool = True,
    group_split: Optional[str] = None,
    min_bin_frac: float = MIN_BIN_FRAC,
) -> list[DecisionVariable]:
    """Candidate-splitting decision variables (their ``find_decision_vars``)."""
    variables: list[DecisionVariable] = []
    seen: set[tuple] = set()

    def add(group: frozenset[int], label: str, positives: set[int], key: tuple) -> None:
        pos = frozenset(positives)
        negatives = {index_of[c.id] for c in survivors} - pos
        if not pos or not negatives:
            return  # degenerate split
        mass = sum(belief.get(i, 0.0) for i in pos)
        if mass < min_bin_frac or mass > 1.0 - min_bin_frac:
            return
        if key in seen:
            return
        seen.add(key)
        variables.append(_variable(group, label, pos, f"dv:{label}"))

    if include_atomic:
        atoms = sorted({a for c in survivors for a in c.z})
        for atom in atoms:
            group = frozenset({atom})
            pos = {index_of[c.id] for c in survivors if group <= c.z}
            add(group, vocab.label_for(group), pos, ("atom", frozenset(pos)))

    if group_split is not None:
        by_id = {c.id: c for c in survivors}
        for cluster in intents:
            members = [by_id[m] for m in cluster.member_ids if m in by_id]
            others = [c for c in survivors if c.id not in set(cluster.member_ids)]
            for group in mine_cluster_group(members, others):
                if group_split == "cluster":
                    pos = {index_of[m] for m in cluster.member_ids if m in index_of}
                else:  # "mask" — the authors' default
                    pos = {index_of[c.id] for c in survivors if group <= c.z}
                add(group, vocab.label_for(group),
                    pos, (cluster.id, frozenset(pos)))
    return variables


@dataclass
class CandidateSession:
    """Repair loop with candidate-level belief and variables (A10, the authors')."""

    candidates: ActionSpace
    sim: np.ndarray
    vocab: FeatureVocabulary
    include_atomic: bool = True
    group_split: Optional[str] = None   # None | "mask" | "cluster"
    clustering: bool = True
    linkage: str = "average"

    surviving_ids: list[str] = field(default_factory=list)
    intents: IntentSet = field(default_factory=list)
    belief: Belief = field(default_factory=dict)
    variables: list[DecisionVariable] = field(default_factory=list)
    ranked: list[DecisionVariable] = field(default_factory=list)
    turn: int = 0

    _index: dict[str, int] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._index = {c.id: i for i, c in enumerate(self.candidates)}
        if not self.surviving_ids:
            self.surviving_ids = [c.id for c in self.candidates]
        self._recompute()

    def _survivors(self) -> ActionSpace:
        return [self.candidates[self._index[cid]] for cid in self.surviving_ids]

    def surviving_indices(self) -> list[int]:
        return [self._index[cid] for cid in self.surviving_ids]

    def _recompute(self) -> None:
        survivors = self._survivors()
        if self.clustering and self.group_split is not None and len(survivors) > 1:
            idx = self.surviving_indices()
            sub = self.sim[np.ix_(idx, idx)]
            k = min(authors_k(len(survivors)), len(survivors))
            self.intents = cluster_candidates(
                survivors, sub, k=k, linkage=self.linkage
            )
        else:
            self.intents = []
        self.belief = frequency_prior(survivors, self._index)
        self.variables = build_candidate_variables(
            survivors, self.intents, self.vocab, self._index, self.belief,
            include_atomic=self.include_atomic, group_split=self.group_split,
        )
        self.ranked = rank_variables(self.belief, self.variables)

    @property
    def terminated(self) -> bool:
        """Their ``stop_mode="sim1"``: survivors functionally identical, else no IG."""
        idx = self.surviving_indices()
        if len(idx) <= 1:
            return True
        if mean_pairwise_similarity(idx, self.sim) >= 1.0 - SIM_STOP_TOL:
            return True
        return not any(v.ig > 1e-12 for v in self.ranked)

    def answer(self, variable_id: str, value: bool) -> None:
        variable = next((v for v in self.variables if v.id == variable_id), None)
        if variable is None:
            raise KeyError(variable_id)
        kept = [
            cid for cid in self.surviving_ids
            if variable.value_of(self._index[cid]) == value
        ]
        if kept and len(kept) < len(self.surviving_ids):
            self.surviving_ids = kept
        self.turn += 1
        self._recompute()


__all__ = [
    "CandidateSession",
    "build_candidate_variables",
    "frequency_prior",
    "MIN_BIN_FRAC",
]
