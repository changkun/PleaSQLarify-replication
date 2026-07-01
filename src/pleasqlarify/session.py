"""Session facade driving the pragmatic-repair loop end to end (spec 08).

A :class:`Session` bundles a frozen action space A, the output-similarity matrix
S, and the current turn state (surviving candidates, intents M_t, belief p_t,
ranked decision variables). It exposes start/next/answer/undo plus the read
accessors the interface (specs 11-14) and the eval oracle (spec 10) consume.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

import numpy as np

from .data.execution import run_query
from .llm.client import LLMClient
from .model.types import (
    ActionSpace,
    Belief,
    Candidate,
    DbSchema,
    DecisionVariable,
    FeatureVocabulary,
    IntentSet,
    ResultTable,
)
from .pipeline import belief as belief_mod
from .pipeline.cluster import cluster_candidates
from .pipeline.decision_vars import atom_probabilities, build_decision_variables
from .pipeline.embed import Embedder, similarity_matrix
from .pipeline.features import extract_features
from .pipeline.generate import generate_candidates
from .pipeline.ranking import rank_variables
from .pipeline.repair_loop import filter_action_space, is_terminated

BeliefInit = Literal["uniform", "frequency"]


@dataclass
class _Snapshot:
    surviving_ids: list[str]
    turn: int


@dataclass
class Session:
    utterance: str
    schema: DbSchema
    db_path: Optional[str]
    candidates: ActionSpace  # frozen A, index-aligned with `sim`
    sim: np.ndarray
    vocab: FeatureVocabulary
    mode: str = "grouped"  # decision-variable mode: grouped | atomic
    belief_init: BeliefInit = "uniform"
    clustering: bool = True
    k: Optional[int] = None
    threshold: float = 0.1

    # ---- turn state (derived; recomputed each turn) ----
    surviving_ids: list[str] = field(default_factory=list)
    intents: IntentSet = field(default_factory=list)
    belief: Belief = field(default_factory=dict)
    variables: list[DecisionVariable] = field(default_factory=list)
    ranked: list[DecisionVariable] = field(default_factory=list)
    turn: int = 0
    history: list[_Snapshot] = field(default_factory=list)

    _index: dict[str, int] = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------ setup
    def __post_init__(self):
        self._index = {c.id: i for i, c in enumerate(self.candidates)}
        if not self.surviving_ids:
            self.surviving_ids = [c.id for c in self.candidates]
        self._recompute()

    def _survivors(self) -> ActionSpace:
        return [self.candidates[self._index[cid]] for cid in self.surviving_ids]

    def surviving_indices(self) -> list[int]:
        """Positions of surviving candidates in ``candidates`` (aligned with ``sim``)."""
        return [self._index[cid] for cid in self.surviving_ids]

    def _recompute(self) -> None:
        survivors = self._survivors()
        if self.clustering:
            idx = [self._index[cid] for cid in self.surviving_ids]
            sub = self.sim[np.ix_(idx, idx)]
            self.intents = cluster_candidates(
                survivors, sub, k=self.k, threshold=self.threshold
            )
        else:
            # baselines without clustering: each surviving query is its own intent
            self.intents = cluster_candidates(
                survivors, np.eye(len(survivors)), k=len(survivors)
            )
        if self.belief_init == "frequency":
            self.belief = belief_mod.frequency_belief(survivors, self.intents)
        else:
            self.belief = belief_mod.uniform_belief(self.intents)
        self.variables = build_decision_variables(
            survivors, self.intents, self.vocab, mode=self.mode
        )
        self.ranked = rank_variables(self.belief, self.variables)

    # ------------------------------------------------------------- loop ops
    @property
    def terminated(self) -> bool:
        return is_terminated(self.intents, self.ranked)

    def next_variable(self) -> Optional[DecisionVariable]:
        if self.terminated:
            return None
        informative = [v for v in self.ranked if v.ig > 1e-12]
        return informative[0] if informative else None

    def answer(self, variable_id: str, value: bool) -> None:
        variable = next((v for v in self.variables if v.id == variable_id), None)
        if variable is None:
            raise KeyError(f"unknown decision variable: {variable_id}")
        self.history.append(_Snapshot(list(self.surviving_ids), self.turn))
        kept = filter_action_space(self._survivors(), variable, value)
        if kept and len(kept) < len(self.surviving_ids):
            self.surviving_ids = [c.id for c in kept]
        # if the answer failed to shrink, keep it recorded but state unchanged (A12d)
        self.turn += 1
        self._recompute()

    def undo(self) -> None:
        if not self.history:
            return
        snap = self.history.pop()
        self.surviving_ids = snap.surviving_ids
        self.turn = snap.turn
        self._recompute()

    # -------------------------------------------------------- read accessors
    def most_probable_cluster(self):
        if not self.belief:
            return self.intents[0] if self.intents else None
        best_id = max(self.belief, key=lambda cid: self.belief[cid])
        return next((c for c in self.intents if c.id == best_id), None)

    def final_query(self) -> Optional[Candidate]:
        cluster = self.most_probable_cluster()
        if cluster is None:
            return None
        return self.candidates[self._index[cluster.representative_id]]

    def predicted_query_atoms(self) -> dict[int, float]:
        selected = self._selected_atoms()
        return atom_probabilities(self._survivors(), selected)

    def _selected_atoms(self) -> frozenset[int]:
        atoms: set[int] = set()
        # atoms common to all survivors are effectively determined
        survivors = self._survivors()
        if survivors:
            common = frozenset.intersection(*[c.z for c in survivors])
            atoms |= common
        return frozenset(atoms)

    def predicted_output(self) -> Optional[ResultTable]:
        cand = self.final_query()
        if cand is None:
            return None
        return cand.result


# --------------------------------------------------------------------------- factory


def build_session(
    utterance: str,
    schema: DbSchema,
    db_path: Optional[str],
    client: LLMClient,
    *,
    embedder: Optional[Embedder] = None,
    n: int = 50,
    temperature: float = 0.7,
    mode: str = "grouped",
    belief_init: BeliefInit = "uniform",
    clustering: bool = True,
    k: Optional[int] = None,
    threshold: float = 0.1,
    results: Optional[dict[str, ResultTable]] = None,
) -> Session:
    """Run steps 1-4 to build an initial :class:`Session`.

    ``results`` lets tests inject precomputed outputs to avoid needing a live DB.
    """
    candidates = generate_candidates(
        utterance, schema, client, n=n, temperature=temperature
    )
    for c in candidates:
        if results is not None and c.sql in results:
            c.result = results[c.sql]
        elif db_path is not None:
            c.result = run_query(db_path, c.sql)
        else:
            c.result = ResultTable(error="no database")
    vocab = extract_features(candidates, schema)
    sim = similarity_matrix(candidates, embedder)
    return Session(
        utterance=utterance,
        schema=schema,
        db_path=db_path,
        candidates=candidates,
        sim=sim,
        vocab=vocab,
        mode=mode,
        belief_init=belief_init,
        clustering=clustering,
        k=k,
        threshold=threshold,
    )


__all__ = ["Session", "build_session", "BeliefInit"]
