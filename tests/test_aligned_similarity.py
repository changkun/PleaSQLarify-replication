"""A4 aligned to the authors' code: row embeddings + optimal alignment.

The authors' live similarity path is
``compute_similarity_matrix_after_optimal_alignment(..., mode="row")``: embed each
row, pad the shorter table with ``<NULL>``, Hungarian-align on ``1 - cosine``, and
average the matched pairs. Our original A4 gap-fill embedded one serialized table
instead, which is what made a shared header dominate the similarity.
"""

from __future__ import annotations

import numpy as np
import pytest

from pleasqlarify.model.types import Candidate, ResultTable
from pleasqlarify.pipeline.embed import (
    DeterministicEmbedder,
    aligned_similarity,
    aligned_similarity_matrix,
    serialize_rows,
    similarity_matrix,
)


def _rt(columns, rows) -> ResultTable:
    return ResultTable(columns=list(columns), rows=[tuple(r) for r in rows])


def _cand(cid, rt) -> Candidate:
    return Candidate(id=cid, sql=cid, z=frozenset(), result=rt)


def test_rows_are_serialized_individually_without_column_names():
    rt = _rt(["Name", "Profit"], [("a", 1), ("b", 2)])
    assert serialize_rows(rt) == ["a 1", "b 2"]
    assert serialize_rows(ResultTable(error="x")) == []
    assert serialize_rows(None) == []


def test_identical_outputs_are_similarity_one_and_empties_match():
    emb = DeterministicEmbedder()
    rows = ["a 1", "b 2"]
    assert aligned_similarity(rows, list(rows), emb) == pytest.approx(1.0)
    assert aligned_similarity([], [], emb) == pytest.approx(1.0)
    # one empty, one not -> no functional agreement
    assert aligned_similarity([], rows, emb) == pytest.approx(0.0)


def test_alignment_makes_similarity_invariant_to_row_order():
    """The point of the Hungarian step: row order must not matter."""
    emb = DeterministicEmbedder()
    a = ["alpha 1", "beta 2", "gamma 3"]
    b = ["gamma 3", "alpha 1", "beta 2"]
    assert aligned_similarity(a, b, emb) == pytest.approx(1.0)


def test_padding_penalises_a_table_with_extra_rows():
    """Nested AMBROSIA golds differ by row count; padding must register that."""
    emb = DeterministicEmbedder()
    small = ["alpha 1", "beta 2"]
    large = ["alpha 1", "beta 2", "zeta 99"]
    partial = aligned_similarity(small, large, emb)
    assert partial < aligned_similarity(small, list(small), emb)
    assert partial > aligned_similarity(small, ["zeta 99"], emb)


def test_matrix_is_symmetric_unit_diagonal_and_bounded():
    emb = DeterministicEmbedder()
    cands = [
        _cand("a", _rt(["X"], [("p",), ("q",)])),
        _cand("b", _rt(["X"], [("q",), ("p",)])),   # same rows, different order
        _cand("c", _rt(["X"], [("z",)])),
        _cand("d", ResultTable(error="boom")),
    ]
    sim = aligned_similarity_matrix(cands, emb)
    assert sim.shape == (4, 4)
    assert np.allclose(sim, sim.T)
    assert np.allclose(np.diag(sim), 1.0)
    assert sim.min() >= 0.0 and sim.max() <= 1.0
    # row-order-permuted duplicates are recognised as functionally identical
    assert sim[0, 1] == pytest.approx(1.0)
    assert sim[0, 2] < sim[0, 1]


def test_row_aligned_style_is_selectable_through_similarity_matrix():
    emb = DeterministicEmbedder()
    cands = [
        _cand("a", _rt(["X"], [("p",), ("q",)])),
        _cand("b", _rt(["X"], [("q",), ("p",)])),
    ]
    via_style = similarity_matrix(cands, emb, style="row_aligned")
    direct = aligned_similarity_matrix(cands, emb)
    assert np.allclose(via_style, direct)
    # the old whole-table style is order-sensitive, so the two disagree here
    table = similarity_matrix(cands, emb, style="header_rows")
    assert not np.allclose(via_style, table)


def test_shared_column_names_no_longer_inflate_similarity_of_distinct_outputs():
    """The 150-sample over-merge mechanism, stated as a comparison of the two A4s."""
    emb = DeterministicEmbedder()
    a = _cand("a", _rt(["OperationID", "Profit", "Months"], [(1, 10, 5)]))
    b = _cand("b", _rt(["OperationID", "Profit", "Months"], [(2, 77, 99)]))
    aligned = aligned_similarity_matrix([a, b], emb)[0, 1]
    whole_table = similarity_matrix([a, b], emb, style="header_rows")[0, 1]
    assert aligned < whole_table


def test_cached_matrix_matches_the_naive_pairwise_computation():
    """The batched/cached matrix must be numerically identical to the naive form."""
    emb = DeterministicEmbedder()
    cands = [
        _cand("a", _rt(["X"], [("p",), ("q",)])),
        _cand("b", _rt(["X"], [("q",), ("p",)])),
        _cand("c", _rt(["X"], [("z",), ("y",), ("w",)])),
        _cand("d", ResultTable(error="boom")),
        _cand("e", _rt(["X"], [("p",)])),
    ]
    fast = aligned_similarity_matrix(cands, emb)
    rows = [serialize_rows(c.result) for c in cands]
    naive = np.eye(len(cands))
    for i in range(len(cands)):
        for j in range(i + 1, len(cands)):
            naive[i, j] = naive[j, i] = aligned_similarity(rows[i], rows[j], emb)
    assert np.allclose(fast, naive, atol=1e-9)
