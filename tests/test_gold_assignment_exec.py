"""The fixed, embedder-independent gold yardstick (A14b, spec 10).

Sweeping the clustering assumptions (A4 serialization, A5 linkage/threshold, A12
termination) requires a ground truth that does *not* move with the embedder being
swept -- otherwise "reached zero gold-label entropy" is redefined in every cell.
These tests pin that property.
"""

from __future__ import annotations

import hashlib

import numpy as np

from pleasqlarify.data.execution import run_query
from pleasqlarify.eval.oracle import assign_gold_intents, assign_gold_intents_exec
from pleasqlarify.model.types import Candidate


def _cand(cid: str, sql: str, db: str) -> Candidate:
    return Candidate(id=cid, sql=sql, z=frozenset(), result=run_query(db, sql))


class _ConstantEmbedder:
    """Pathological embedder: every output is the same point (merges everything)."""

    def embed(self, texts: list[str]) -> np.ndarray:
        v = np.zeros((len(texts), 4))
        v[:, 0] = 1.0
        return v


class _NoiseEmbedder:
    """Pathological embedder: assignment driven by arbitrary per-text hashing."""

    def embed(self, texts: list[str]) -> np.ndarray:
        v = np.zeros((len(texts), 8))
        for i, t in enumerate(texts):
            # stable across processes (unlike hash()), so the test is deterministic
            h = hashlib.blake2b(t.encode(), digest_size=4).digest()
            v[i, int.from_bytes(h, "little") % 8] = 1.0
        return v


def test_exact_output_match_assigns_the_matching_gold(film_db):
    golds = [
        "SELECT Opinion FROM Reviews",
        "SELECT AudienceReviews FROM Reviews",
    ]
    cands = [
        _cand("a", "SELECT Opinion FROM Reviews", film_db),
        _cand("b", "SELECT AudienceReviews FROM Reviews", film_db),
        # textual variant of gold 0 -> same executed rows -> same label
        _cand("c", "SELECT R.Opinion FROM Reviews R", film_db),
    ]
    assign = assign_gold_intents_exec(cands, golds, film_db)
    assert assign == {"a": 0, "b": 1, "c": 0}


def test_assignment_is_invariant_to_the_embedder_under_test(film_db):
    """The whole point: the yardstick must not move when the swept embedder does."""
    golds = [
        "SELECT Opinion FROM Reviews",
        "SELECT AudienceReviews FROM Reviews",
    ]
    cands = [
        _cand("a", "SELECT Opinion FROM Reviews", film_db),
        _cand("b", "SELECT AudienceReviews FROM Reviews", film_db),
    ]

    fixed = assign_gold_intents_exec(cands, golds, film_db)
    # the embedding-based assignment is *not* stable across embedders ...
    emb_constant = assign_gold_intents(cands, golds, film_db, _ConstantEmbedder())
    emb_noise = assign_gold_intents(cands, golds, film_db, _NoiseEmbedder())
    assert emb_constant != fixed or emb_noise != fixed, (
        "fixture too weak: embedding assignment must be shown to be embedder-dependent"
    )
    # ... while the exec-match assignment takes no embedder at all and is exact.
    assert fixed == {"a": 0, "b": 1}


def test_partial_overlap_falls_back_to_jaccard_and_disjoint_is_unassigned(film_db):
    golds = [
        "SELECT Title FROM Film WHERE Genre='Drama'",     # Pulp Fiction, Heat
        "SELECT Title FROM Film WHERE Genre='Comedy'",    # Airplane
    ]
    cands = [
        # overlaps gold 0 on one row, gold 1 on none -> gold 0
        _cand("a", "SELECT Title FROM Film WHERE Title='Heat'", film_db),
        # overlaps neither gold -> unassigned, excluded from the entropy
        _cand("b", "SELECT Genre FROM Film WHERE Genre='Drama'", film_db),
        # an erroring query is never labelled
        _cand("c", "SELECT nope FROM Film", film_db),
    ]
    assign = assign_gold_intents_exec(cands, golds, film_db)
    assert assign["a"] == 0
    assert "b" not in assign
    assert "c" not in assign


def test_assignment_is_deterministic_under_repetition(film_db):
    golds = ["SELECT Opinion FROM Reviews", "SELECT CriticName FROM Reviews"]
    cands = [_cand("a", "SELECT Opinion FROM Reviews", film_db)]
    runs = [assign_gold_intents_exec(cands, golds, film_db) for _ in range(5)]
    assert all(r == runs[0] for r in runs)
