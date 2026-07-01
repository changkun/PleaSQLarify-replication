"""Benchmark runner reproducing Figure 5 (spec 10).

Runs all five conditions across samples with the simulated-user oracle over a
fixed candidate pool, records per-turn gold-label entropy and functional output
similarity, and aggregates to median + 95% bootstrap CI per ambiguity type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

from ..llm.client import LLMClient
from ..model.types import DbSchema
from ..pipeline.embed import Embedder
from ..session import build_session
from .conditions import Condition, five_conditions
from .metrics import bootstrap_ci, gold_label_entropy, mean_pairwise_similarity
from .oracle import GoldOracle, assign_gold_intents


@dataclass
class EvalSample:
    sample_id: str
    ambiguity_type: str
    utterance: str
    schema: DbSchema
    db_path: str
    gold_sqls: list[str]
    client: LLMClient
    results: dict | None = None  # optional injected outputs (offline)


@dataclass
class RunRow:
    condition: str
    ambiguity_type: str
    sample_id: str
    gold: int
    turn: int
    entropy: float
    similarity: float


def _run_one(
    session, condition: Condition, oracle: GoldOracle, gold_assignment, max_turns: int
) -> list[tuple[int, float, float]]:
    rows: list[tuple[int, float, float]] = []
    for turn in range(max_turns + 1):
        ent = gold_label_entropy(session.surviving_ids, gold_assignment)
        sim = mean_pairwise_similarity(session.surviving_indices(), session.sim)
        rows.append((turn, ent, sim))
        if session.terminated:
            break
        v = condition.select(session)
        if v is None:
            break
        session.answer(v.id, oracle.answer(v))
    # forward-fill to max_turns (A15b): terminated runs hold their final value
    last = rows[-1]
    for t in range(last[0] + 1, max_turns + 1):
        rows.append((t, last[1], last[2]))
    return rows


def run_benchmark(
    samples: list[EvalSample],
    conditions: list[Condition] | None = None,
    max_turns: int = 10,
    embedder: Embedder | None = None,
    seed: int = 0,
) -> list[RunRow]:
    conditions = conditions or five_conditions(seed)
    out: list[RunRow] = []
    for sample in samples:
        for cond in conditions:
            for gi, gold_sql in enumerate(sample.gold_sqls):
                session = build_session(
                    sample.utterance,
                    sample.schema,
                    sample.db_path,
                    sample.client,
                    embedder=embedder,
                    mode=cond.mode,
                    clustering=cond.clustering,
                    results=sample.results,
                )
                assignment = assign_gold_intents(
                    session.candidates, sample.gold_sqls, sample.db_path, embedder
                )
                oracle = GoldOracle(gold_sql, sample.schema, session.vocab)
                for turn, ent, sim in _run_one(
                    session, cond, oracle, assignment, max_turns
                ):
                    out.append(
                        RunRow(
                            cond.name, sample.ambiguity_type, sample.sample_id,
                            gi, turn, ent, sim,
                        )
                    )
    return out


def aggregate(rows: list[RunRow]) -> dict:
    """Median + 95% bootstrap CI of entropy and similarity per (condition, type, turn)."""
    groups: dict[tuple, dict[str, list[float]]] = {}
    for r in rows:
        key = (r.condition, r.ambiguity_type, r.turn)
        g = groups.setdefault(key, {"entropy": [], "similarity": []})
        g["entropy"].append(r.entropy)
        g["similarity"].append(r.similarity)
    agg: dict[tuple, dict] = {}
    for key, vals in groups.items():
        agg[key] = {
            "entropy": bootstrap_ci(vals["entropy"]),
            "similarity": bootstrap_ci(vals["similarity"]),
            "n": len(vals["entropy"]),
        }
    return agg


def mean_convergence_turn(rows: list[RunRow], condition: str, eps: float = 1e-9) -> float:
    """Median first turn at which entropy reaches ~0 for a condition."""
    per_run: dict[tuple, int] = {}
    max_turn = max(r.turn for r in rows)
    for r in rows:
        if r.condition != condition:
            continue
        run_key = (r.sample_id, r.gold)
        if r.entropy <= eps and run_key not in per_run:
            per_run[run_key] = r.turn
    if not per_run:
        return float(max_turn)
    return float(median(per_run.values()))


__all__ = [
    "EvalSample",
    "RunRow",
    "run_benchmark",
    "aggregate",
    "mean_convergence_turn",
]
