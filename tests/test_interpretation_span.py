"""Interpretation-span measurement, incl. the two bugs it exists to avoid.

Both failure modes below produced wrong replication headlines before being caught,
so each gets an explicit regression test.
"""

from __future__ import annotations

from pleasqlarify.eval.interpretation_span import (
    SpanReport,
    output_values,
    realised_interpretations,
    sample_span,
)
from pleasqlarify.data.execution import run_query
from pleasqlarify.model.types import Candidate, ResultTable


def _vals(*rows: tuple) -> set[str]:
    return {str(v) for row in rows for v in row}


# ------------------------------------------------------------------ regressions


def test_nested_golds_are_still_distinguishable():
    """REGRESSION: 'distinctive values' made the subset gold uncoverable by
    construction, forcing measured span to 0 on 102/150 AMBROSIA samples."""
    gold0 = {"A", "B"}            # filter on both sides
    gold1 = {"A", "B", "C"}       # filter on one side -> strict superset
    exact_gold0 = {"A", "B"}
    exact_gold1 = {"A", "B", "C"}

    assert realised_interpretations([exact_gold0], [gold0, gold1]) == {0}
    assert realised_interpretations([exact_gold1], [gold0, gold1]) == {1}
    # a pool holding both readings spans both, despite the nesting
    assert realised_interpretations([exact_gold0, exact_gold1], [gold0, gold1]) == {0, 1}


def test_wider_projection_still_realises_its_interpretation():
    """REGRESSION: exact row-match rejected a correct candidate that projected an
    extra column (FirstName, LastName vs LastName)."""
    gold0 = {"Doe", "Green"}
    gold1 = {"Black", "Brown", "Doe", "Green"}
    candidate = {"Jack", "Green", "John", "Doe"}  # extra first names, gold0 reading
    assert realised_interpretations([candidate], [gold0, gold1]) == {0}


def test_superset_candidate_does_not_get_credit_for_the_narrower_gold():
    gold0, gold1 = {"A", "B"}, {"A", "B", "C"}
    # contains gold0's values but also gold1's extra -> it is the gold1 reading only
    assert realised_interpretations([{"A", "B", "C"}], [gold0, gold1]) == {1}


# ------------------------------------------------------------------- behaviour


def test_degenerate_outputs_realise_nothing():
    assert output_values(ResultTable(error="boom")) == set()
    assert output_values(ResultTable(columns=["x"], rows=[])) == set()
    assert output_values(None) == set()
    assert realised_interpretations([set()], [{"A"}, {"B"}]) == set()


def test_empty_gold_is_never_credited():
    assert realised_interpretations([{"A"}], [set(), {"A"}]) == {1}


def test_sample_span_drops_samples_whose_golds_are_output_identical(film_db):
    def cand(sql):
        return Candidate(id=sql, sql=sql, z=frozenset(), result=run_query(film_db, sql))

    same = ["SELECT Title FROM Film", "SELECT Title FROM Film ORDER BY Title"]
    assert sample_span([cand("SELECT Title FROM Film")], same, film_db) is None

    different = [
        "SELECT Title FROM Film WHERE Genre='Drama'",
        "SELECT Title FROM Film WHERE Genre='Comedy'",
    ]
    covered = sample_span(
        [cand("SELECT Title FROM Film WHERE Genre='Comedy'")], different, film_db
    )
    assert covered == {1}


def test_sample_span_detects_a_pool_that_spans_both_readings(film_db):
    def cand(sql):
        return Candidate(id=sql, sql=sql, z=frozenset(), result=run_query(film_db, sql))

    golds = [
        "SELECT Title FROM Film WHERE Genre='Drama'",
        "SELECT Title FROM Film WHERE Genre='Comedy'",
    ]
    pool = [
        cand("SELECT Title FROM Film WHERE Genre='Drama'"),
        cand("SELECT Title FROM Film WHERE Genre='Comedy'"),
    ]
    assert sample_span(pool, golds, film_db) == {0, 1}


def test_span_report_counts_and_rate():
    r = SpanReport()
    r.add({0, 1})
    r.add({0})
    r.add(set())
    r.add({0, 1})
    assert (r.usable, r.span_two_plus, r.span_one, r.span_none) == (4, 2, 1, 1)
    assert r.span_rate == 0.5
    assert SpanReport().span_rate == 0.0
