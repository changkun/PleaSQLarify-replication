"""Assumption sweep over A4 (serialization), A5 (linkage/threshold) and A12
(termination) — spec 16.

Answers one question: is the non-reproduction of the paper's clustering advantage
a property of AMBROSIA, or of the gap-fills we chose for the decisions the paper
left unstated?

Two design constraints come straight from spec 16 and are not negotiable here:

1. **Fixed yardstick.** Every cell is scored with
   :func:`assign_gold_intents_exec`, which derives gold labels from executed
   SQLite output alone. The default embedding-based assignment would move with the
   very embedder the sweep varies, making cells incomparable.
2. **Zero new LLM calls.** Generations are replayed from a completed run's
   ``llm/<model>/<sample>/completions.json``, so the sweep costs CPU only.

Work is shared aggressively: candidates are built and executed once per sample,
the similarity matrix once per (sample, serialization), and the baselines once in
total — they are invariant to every swept axis under the fixed yardstick.
"""

from __future__ import annotations

import concurrent.futures as cf
import itertools
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import numpy as np

from ..data.execution import run_query
from ..eval.conditions import Condition, five_conditions
from ..eval.metrics import gold_label_entropy
from ..eval.oracle import GoldOracle, assign_gold_intents_exec
from ..llm.client import CachedLLMClient
from ..model.types import ResultTable
from ..pipeline.embed import Embedder, similarity_matrix
from ..pipeline.generate import build_prompt
from ..session import build_session

# ------------------------------------------------------------------ grid spec

WITHIN_SPEC_STYLES = ("header_rows", "values_only", "columns_only", "cells_sorted")
BEYOND_SPEC_STYLES = ("rowset_jaccard",)
THRESHOLDS = (0.02, 0.05, 0.10, 0.20, 0.40)
LINKAGES = ("average", "complete", "single")
TERMINATIONS = ("cluster_or_uninformative", "uninformative_only")

OURS = "Ours: Clustering + EIG + Feature Grouping"
REFERENCE = "Baseline ERG + Atomic"


@dataclass(frozen=True)
class Cell:
    style: str
    threshold: float
    linkage: str
    termination: str

    @property
    def tag(self) -> str:
        """within-spec cells may claim a replication; beyond-spec ones may not."""
        return "beyond_spec" if self.style in BEYOND_SPEC_STYLES else "within_spec"

    @property
    def id(self) -> str:
        return f"{self.style}|t{self.threshold}|{self.linkage}|{self.termination}"


def build_grid(include_beyond_spec: bool = True) -> list[Cell]:
    styles = list(WITHIN_SPEC_STYLES) + (
        list(BEYOND_SPEC_STYLES) if include_beyond_spec else []
    )
    return [
        Cell(s, t, l, term)
        for s, t, l, term in itertools.product(styles, THRESHOLDS, LINKAGES, TERMINATIONS)
    ]


# ------------------------------------------------------- beyond-spec similarity


def _row_multiset(rt: Optional[ResultTable]) -> Counter:
    if rt is None or rt.is_error or rt.is_empty:
        return Counter()
    return Counter("\x1f".join("" if v is None else str(v) for v in row) for row in rt.rows)


def rowset_jaccard_similarity(candidates) -> np.ndarray:
    """S from row-multiset overlap — **beyond-spec**: replaces the paper's embedding.

    Degenerate outputs (error/empty) keep the sentinel behaviour of the embedding
    path: they are mutually similar and dissimilar to everything value-bearing.
    """
    keys = [_row_multiset(c.result) for c in candidates]
    n = len(keys)
    sim = np.eye(n)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = keys[i], keys[j]
            if not a and not b:
                s = 1.0
            elif not a or not b:
                s = 0.0
            else:
                union = sum((a | b).values())
                s = sum((a & b).values()) / union if union else 0.0
            sim[i, j] = sim[j, i] = s
    return sim


# ------------------------------------------------------------------- sampling


def stratified_split(samples, seed: int = 0) -> tuple[list, list]:
    """50/50 dev/held-out split by sample, stratified by ambiguity type (spec 16)."""
    dev, held = [], []
    by_type = defaultdict(list)
    for s in sorted(samples, key=lambda s: s.sample_id):
        by_type[s.ambiguity_type].append(s)
    rng = np.random.default_rng(seed)
    for _type, group in sorted(by_type.items()):
        order = rng.permutation(len(group))
        for rank, idx in enumerate(order):
            (dev if rank % 2 == 0 else held).append(group[idx])
    return dev, held


# --------------------------------------------------------------- per-sample prep


@dataclass
class PreparedSample:
    sample_id: str
    ambiguity_type: str
    utterance: str
    schema: object
    db_path: str
    gold_sqls: list[str]
    completions: list[str]
    prompt: str
    assignment: dict[str, int] = field(default_factory=dict)
    sims: dict[str, np.ndarray] = field(default_factory=dict)  # style -> S


def prepare_sample(sample, completions: list[str], styles: Iterable[str],
                   embedder: Embedder) -> Optional[PreparedSample]:
    """Build candidates once, then S once per serialization style."""
    prompt = build_prompt(sample.utterance, sample.schema)
    client = CachedLLMClient({prompt: completions})
    base = build_session(
        sample.utterance, sample.schema, sample.db_path, client,
        embedder=embedder, mode="grouped", clustering=True,
    )
    if not base.candidates:
        return None
    prepared = PreparedSample(
        sample_id=sample.sample_id,
        ambiguity_type=sample.ambiguity_type,
        utterance=sample.utterance,
        schema=sample.schema,
        db_path=sample.db_path,
        gold_sqls=[g.sql for g in sample.gold_queries],
        completions=completions,
        prompt=prompt,
    )
    prepared.assignment = assign_gold_intents_exec(
        base.candidates, prepared.gold_sqls, sample.db_path
    )
    for style in styles:
        if style == "rowset_jaccard":
            prepared.sims[style] = rowset_jaccard_similarity(base.candidates)
        else:
            prepared.sims[style] = similarity_matrix(base.candidates, embedder, style=style)
    return prepared


# ------------------------------------------------------------------ evaluation


@dataclass
class RunOutcome:
    entropies: list[float]     # per turn, forward-filled to max_turns
    reached_zero: bool
    merge_ratio: float         # #clusters / #survivors at turn 0
    initially_ambiguous: bool


def evaluate_run(prepared: PreparedSample, cond: Condition, gold_sql: str,
                 sim: np.ndarray, cell: Optional[Cell], max_turns: int) -> RunOutcome:
    client = CachedLLMClient({prepared.prompt: prepared.completions})
    sess = build_session(
        prepared.utterance, prepared.schema, prepared.db_path, client,
        mode=cond.mode, clustering=cond.clustering, sim=sim,
        threshold=cell.threshold if cell else 0.1,
        linkage=cell.linkage if cell else "average",
        termination=cell.termination if cell else "cluster_or_uninformative",
    )
    oracle = GoldOracle(gold_sql, prepared.schema, sess.vocab)
    assign = prepared.assignment

    n_surv0 = max(len(sess.surviving_ids), 1)
    merge_ratio = len(sess.intents) / n_surv0
    entropies = []
    for _t in range(max_turns + 1):
        entropies.append(gold_label_entropy(sess.surviving_ids, assign))
        if sess.terminated:
            break
        v = cond.select(sess)
        if v is None:
            break
        sess.answer(v.id, oracle.answer(v))
    last = entropies[-1]
    entropies += [last] * (max_turns + 1 - len(entropies))
    return RunOutcome(
        entropies=entropies,
        reached_zero=any(e <= 1e-9 for e in entropies),
        merge_ratio=merge_ratio,
        initially_ambiguous=entropies[0] > 1e-9,
    )


@dataclass
class CellResult:
    cell_id: str
    tag: str
    condition: str
    split: str
    n_runs: int
    n_ambiguous: int
    reach_zero_rate: float
    mean_entropy_by_turn: list[float]
    merge_ratio: float

    def as_row(self) -> dict:
        d = dict(self.__dict__)
        d["mean_entropy_by_turn"] = ";".join(f"{e:.6f}" for e in self.mean_entropy_by_turn)
        return d


def _aggregate(cell_id, tag, condition, split, outcomes: list[RunOutcome]) -> CellResult:
    amb = [o for o in outcomes if o.initially_ambiguous]
    n_turns = len(outcomes[0].entropies) if outcomes else 0
    mean_by_turn = [
        float(np.mean([o.entropies[t] for o in amb])) if amb else 0.0
        for t in range(n_turns)
    ]
    return CellResult(
        cell_id=cell_id,
        tag=tag,
        condition=condition,
        split=split,
        n_runs=len(outcomes),
        n_ambiguous=len(amb),
        reach_zero_rate=(sum(o.reached_zero for o in amb) / len(amb)) if amb else 0.0,
        mean_entropy_by_turn=mean_by_turn,
        merge_ratio=float(np.mean([o.merge_ratio for o in amb])) if amb else 0.0,
    )


def evaluate_cell(prepared_list: list[PreparedSample], cell: Cell, conditions: list[Condition],
                  split: str, max_turns: int) -> list[CellResult]:
    results = []
    for cond in conditions:
        outcomes = []
        for p in prepared_list:
            sim = p.sims[cell.style]
            for gold_sql in p.gold_sqls:
                outcomes.append(evaluate_run(p, cond, gold_sql, sim, cell, max_turns))
        results.append(_aggregate(cell.id, cell.tag, cond.name, split, outcomes))
    return results


def evaluate_baselines(prepared_list: list[PreparedSample], conditions: list[Condition],
                       split: str, max_turns: int, style: str) -> list[CellResult]:
    """Baselines are invariant to every swept axis, so they are computed once."""
    results = []
    for cond in conditions:
        outcomes = []
        for p in prepared_list:
            sim = p.sims[style]
            for gold_sql in p.gold_sqls:
                outcomes.append(evaluate_run(p, cond, gold_sql, sim, None, max_turns))
        results.append(_aggregate("baseline", "reference", cond.name, split, outcomes))
    return results


__all__ = [
    "Cell",
    "CellResult",
    "RunOutcome",
    "PreparedSample",
    "build_grid",
    "stratified_split",
    "prepare_sample",
    "evaluate_run",
    "evaluate_cell",
    "evaluate_baselines",
    "rowset_jaccard_similarity",
    "WITHIN_SPEC_STYLES",
    "BEYOND_SPEC_STYLES",
    "THRESHOLDS",
    "LINKAGES",
    "TERMINATIONS",
    "OURS",
    "REFERENCE",
]
