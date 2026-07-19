"""The three swept assumption axes are real knobs, not inert parameters (A4/A5/A12).

A sweep over parameters that do not change behaviour would produce a flat grid
that *looks* like evidence ("no configuration recovers the advantage") while
actually testing nothing. Each test here pins the mechanism the axis is supposed
to control, in the direction the sweep's interpretation depends on.
"""

from __future__ import annotations

import numpy as np
import pytest

from pleasqlarify.model.types import Candidate, Cluster, DecisionVariable, ResultTable
from pleasqlarify.pipeline.cluster import cluster_candidates
from pleasqlarify.pipeline.embed import SERIALIZATION_STYLES, serialize_result
from pleasqlarify.pipeline.repair_loop import is_terminated


def _rt(columns, rows) -> ResultTable:
    return ResultTable(columns=list(columns), rows=[tuple(r) for r in rows])


# --------------------------------------------------------------- A4 serialization


def test_serialization_styles_are_distinct_and_deterministic():
    rt = _rt(["Name", "Profit"], [("a", 1), ("b", 2)])
    texts = {s: serialize_result(rt, style=s) for s in SERIALIZATION_STYLES}
    assert len(set(texts.values())) == len(SERIALIZATION_STYLES), texts
    for s in SERIALIZATION_STYLES:
        assert serialize_result(rt, style=s) == texts[s]


def test_values_only_drops_column_names_that_inflate_similarity():
    """The verified over-merge mechanism: shared column headers dominate the text."""
    a = _rt(["OperationID", "Profit", "TotalMonths"], [(1, 10, 5)])
    b = _rt(["OperationID", "Profit", "MonthsSinceStart"], [(1, 10, 99)])
    # default style carries the shared header tokens ...
    assert "OperationID" in serialize_result(a, style="header_rows")
    # ... values_only strips them, leaving only the genuinely differing cell.
    assert "OperationID" not in serialize_result(a, style="values_only")
    assert serialize_result(a, style="values_only") != serialize_result(
        b, style="values_only"
    )


def test_columns_only_ignores_values_and_unknown_style_raises():
    a = _rt(["X"], [(1,)])
    b = _rt(["X"], [(2,)])
    assert serialize_result(a, style="columns_only") == serialize_result(
        b, style="columns_only"
    )
    with pytest.raises(ValueError):
        serialize_result(a, style="nope")


def test_degenerate_outputs_stay_a_single_sentinel_class_in_every_style():
    err, empty = ResultTable(error="boom"), _rt(["X"], [])
    for s in SERIALIZATION_STYLES:
        assert serialize_result(err, style=s) == serialize_result(empty, style=s)


# ------------------------------------------------------------------- A5 linkage


def _cands(n: int) -> list[Candidate]:
    return [Candidate(id=f"c{i}", sql=f"S{i}", z=frozenset()) for i in range(n)]


def test_complete_linkage_resists_the_chain_that_merges_under_single_linkage():
    """Three outputs where 0-1 and 1-2 are close but 0-2 is far apart."""
    sim = np.array(
        [
            [1.00, 0.95, 0.50],
            [0.95, 1.00, 0.95],
            [0.50, 0.95, 1.00],
        ]
    )
    single = cluster_candidates(_cands(3), sim.copy(), threshold=0.1, linkage="single")
    complete = cluster_candidates(_cands(3), sim.copy(), threshold=0.1, linkage="complete")
    # single linkage chains 0-1-2 into one cluster; complete linkage refuses,
    # because the 0-2 pair is far. This is the over-merge knob.
    assert len(single) == 1
    assert len(complete) > len(single)


def test_lower_threshold_never_produces_fewer_clusters():
    rng = np.random.default_rng(0)
    v = rng.random((8, 5))
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    sim = v @ v.T
    sim = (sim + sim.T) / 2
    np.fill_diagonal(sim, 1.0)
    counts = [
        len(cluster_candidates(_cands(8), sim.copy(), threshold=t, linkage="average"))
        for t in (0.01, 0.05, 0.1, 0.3, 0.9)
    ]
    assert counts == sorted(counts, reverse=True), counts


def test_unknown_linkage_raises():
    with pytest.raises(ValueError):
        cluster_candidates(_cands(2), np.eye(2), threshold=0.1, linkage="ward")


# --------------------------------------------------------------- A12 termination


def _var(ig: float) -> DecisionVariable:
    return DecisionVariable(id="v0", group=frozenset({0}), label="v", ig=ig)


def test_uninformative_only_keeps_asking_inside_an_over_merged_single_cluster():
    """The exact failure mode found at 150-sample scale: one cluster, several intents."""
    one_cluster = [Cluster(id=0, member_ids=["a", "b"], representative_id="a")]
    informative = [_var(0.5)]
    # the default rule stops as soon as everything is one functional class ...
    assert is_terminated(one_cluster, informative, rule="cluster_or_uninformative")
    # ... while uninformative_only keeps going while a question still separates them.
    assert not is_terminated(one_cluster, informative, rule="uninformative_only")


def test_both_rules_stop_when_nothing_is_informative():
    two = [
        Cluster(id=0, member_ids=["a"], representative_id="a"),
        Cluster(id=1, member_ids=["b"], representative_id="b"),
    ]
    for rule in ("cluster_or_uninformative", "uninformative_only"):
        assert is_terminated(two, [_var(0.0)], rule=rule)


def test_unknown_termination_rule_raises():
    with pytest.raises(ValueError):
        is_terminated([], [], rule="whenever")
