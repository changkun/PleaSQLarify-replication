"""Simulated-user oracle and gold-intent assignment (spec 10).

The oracle plays a user whose intent is one gold interpretation and answers each
surfaced decision variable by whether the gold query carries it (A13). Gold-intent
assignment labels every generated candidate with its nearest gold interpretation
by functional output similarity (A14).
"""

from __future__ import annotations

import numpy as np

from ..data.execution import run_query
from ..model.types import ActionSpace, DbSchema, DecisionVariable, ResultTable
from ..pipeline.embed import Embedder, DeterministicEmbedder, serialize_result
from ..pipeline.features import _atoms_for, parse_and_qualify


def gold_atom_payloads(sql: str, schema: DbSchema) -> set[str]:
    """The set of canonical atom payloads a (gold) query contains."""
    ast = parse_and_qualify(sql, schema)
    if ast is None:
        return set()
    return {payload for _, payload in _atoms_for(ast)}


class GoldOracle:
    """Answers decision variables consistently with one gold interpretation (A13)."""

    def __init__(self, gold_sql: str, schema: DbSchema, vocab):
        self.payloads = gold_atom_payloads(gold_sql, schema)
        self.vocab = vocab

    def answer(self, variable: DecisionVariable) -> bool:
        group_payloads = {self.vocab.features[i].payload for i in variable.group}
        return group_payloads <= self.payloads


def assign_gold_intents(
    candidates: ActionSpace,
    gold_sqls: list[str],
    db_path: str,
    embedder: Embedder | None = None,
) -> dict[str, int]:
    """Map each candidate id -> index of its nearest gold interpretation (A14)."""
    embedder = embedder or DeterministicEmbedder()
    gold_results = [run_query(db_path, g) for g in gold_sqls]
    gold_vecs = embedder.embed([serialize_result(r) for r in gold_results])

    cand_vecs = embedder.embed(
        [serialize_result(c.result or ResultTable(error="unrun")) for c in candidates]
    )
    # cosine (vectors are L2-normalized)
    sims = cand_vecs @ gold_vecs.T
    assignment: dict[str, int] = {}
    for i, c in enumerate(candidates):
        assignment[c.id] = int(np.argmax(sims[i]))
    return assignment


__all__ = ["gold_atom_payloads", "GoldOracle", "assign_gold_intents"]
