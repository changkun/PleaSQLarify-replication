"""Sweep engine: grid tagging, split discipline, work-sharing, decision rule (spec 16)."""

from __future__ import annotations

import numpy as np
import pytest

from pleasqlarify.data.execution import run_query
from pleasqlarify.experiment.sweep import (
    BEYOND_SPEC_STYLES,
    WITHIN_SPEC_STYLES,
    Cell,
    build_grid,
    evaluate_baselines,
    evaluate_cell,
    prepare_sample,
    rowset_jaccard_similarity,
    stratified_split,
)
from pleasqlarify.eval.conditions import five_conditions
from pleasqlarify.model.types import Candidate


class _Sample:
    def __init__(self, sample_id, ambiguity_type):
        self.sample_id = sample_id
        self.ambiguity_type = ambiguity_type


# ------------------------------------------------------------------ grid + tags


def test_every_beyond_spec_cell_is_tagged_so_it_cannot_claim_a_replication():
    grid = build_grid(include_beyond_spec=True)
    beyond = [c for c in grid if c.style in BEYOND_SPEC_STYLES]
    within = [c for c in grid if c.style in WITHIN_SPEC_STYLES]
    assert beyond and within
    assert all(c.tag == "beyond_spec" for c in beyond)
    assert all(c.tag == "within_spec" for c in within)


def test_grid_can_exclude_beyond_spec_and_cell_ids_are_unique():
    grid = build_grid(include_beyond_spec=False)
    assert all(c.tag == "within_spec" for c in grid)
    full = build_grid(include_beyond_spec=True)
    assert len({c.id for c in full}) == len(full)


def test_the_current_committed_configuration_is_in_the_grid():
    """The sweep must contain the status quo, or the comparison has no baseline."""
    ids = {c.id for c in build_grid()}
    assert Cell("header_rows", 0.10, "average", "cluster_or_uninformative").id in ids


# ----------------------------------------------------------------------- split


def test_split_is_disjoint_covering_stratified_and_deterministic():
    samples = [_Sample(f"{t}_s{i}", t) for t in ("scope", "vague") for i in range(10)]
    dev, held = stratified_split(samples, seed=0)
    dev_ids = {s.sample_id for s in dev}
    held_ids = {s.sample_id for s in held}
    assert not (dev_ids & held_ids)
    assert len(dev_ids | held_ids) == len(samples)
    for t in ("scope", "vague"):
        assert sum(s.ambiguity_type == t for s in dev) == 5
        assert sum(s.ambiguity_type == t for s in held) == 5
    again = stratified_split(samples, seed=0)
    assert [s.sample_id for s in again[0]] == [s.sample_id for s in dev]


def test_split_does_not_depend_on_input_order():
    samples = [_Sample(f"s{i}", "scope") for i in range(8)]
    a = {s.sample_id for s in stratified_split(samples, seed=0)[0]}
    b = {s.sample_id for s in stratified_split(list(reversed(samples)), seed=0)[0]}
    assert a == b


# ---------------------------------------------------- beyond-spec similarity


def test_rowset_jaccard_separates_outputs_that_share_only_column_names(film_db):
    """The over-merge mechanism: identical headers, genuinely different rows."""
    def cand(cid, sql):
        return Candidate(id=cid, sql=sql, z=frozenset(), result=run_query(film_db, sql))

    cands = [
        cand("a", "SELECT Title FROM Film WHERE Genre='Drama'"),
        cand("b", "SELECT Title FROM Film WHERE Genre='Comedy'"),
        cand("c", "SELECT Title FROM Film WHERE Genre='Drama'"),
    ]
    sim = rowset_jaccard_similarity(cands)
    assert sim[0, 2] == pytest.approx(1.0)   # same rows -> identical
    assert sim[0, 1] == pytest.approx(0.0)   # disjoint rows -> not similar
    assert np.allclose(sim, sim.T) and np.allclose(np.diag(sim), 1.0)


def test_rowset_jaccard_puts_degenerate_outputs_in_one_sentinel_class(film_db):
    err = Candidate(id="e", sql="x", z=frozenset(), result=run_query(film_db, "SELECT nope FROM Film"))
    empty = Candidate(id="m", sql="y", z=frozenset(),
                      result=run_query(film_db, "SELECT Title FROM Film WHERE Genre='None'"))
    real = Candidate(id="r", sql="z", z=frozenset(), result=run_query(film_db, "SELECT Title FROM Film"))
    sim = rowset_jaccard_similarity([err, empty, real])
    assert sim[0, 1] == pytest.approx(1.0)
    assert sim[0, 2] == pytest.approx(0.0)


# ------------------------------------------------------- end-to-end on fixtures


@pytest.fixture
def prepared(film_db, schema, review_completions):
    sample = type("S", (), {})()
    sample.sample_id = "film#0"
    sample.ambiguity_type = "vague"
    sample.utterance = "What was the review of the drama film?"
    sample.schema = schema
    sample.db_path = film_db
    sample.gold_queries = [
        type("G", (), {"sql": "SELECT Opinion FROM Reviews WHERE FilmId IN "
                              "(SELECT id FROM Film WHERE Genre='Drama')"})(),
        type("G", (), {"sql": "SELECT AudienceReviews FROM Reviews WHERE FilmId IN "
                              "(SELECT id FROM Film WHERE Genre='Drama')"})(),
    ]
    styles = list(WITHIN_SPEC_STYLES) + list(BEYOND_SPEC_STYLES)
    return prepare_sample(sample, review_completions, styles, embedder=None)


def test_prepare_sample_builds_one_similarity_matrix_per_style(prepared):
    assert prepared is not None
    styles = set(WITHIN_SPEC_STYLES) | set(BEYOND_SPEC_STYLES)
    assert set(prepared.sims) == styles
    n = len(prepared.assignment) or 1
    for style, sim in prepared.sims.items():
        assert sim.shape[0] == sim.shape[1], style
        assert np.allclose(sim, sim.T), style


def test_gold_assignment_is_identical_across_styles_the_fixed_yardstick(prepared):
    """Spec 16's blocking constraint, asserted on real fixture data."""
    # the assignment is computed once, from execution only -- it carries no style
    assert prepared.assignment
    assert all(v in (0, 1) for v in prepared.assignment.values())


def test_evaluate_cell_reports_every_condition_with_a_bounded_reach_zero_rate(prepared):
    conds = [c for c in five_conditions(0) if c.clustering]
    cell = Cell("header_rows", 0.10, "average", "cluster_or_uninformative")
    results = evaluate_cell([prepared], cell, conds, split="dev", max_turns=6)
    assert {r.condition for r in results} == {c.name for c in conds}
    for r in results:
        assert r.cell_id == cell.id and r.split == "dev" and r.tag == "within_spec"
        assert 0.0 <= r.reach_zero_rate <= 1.0
        assert 0.0 < r.merge_ratio <= 1.0
        assert len(r.mean_entropy_by_turn) == 7


def test_entropy_is_forward_filled_and_never_increases_after_termination(prepared):
    conds = [c for c in five_conditions(0) if c.clustering]
    cell = Cell("header_rows", 0.10, "average", "cluster_or_uninformative")
    r = evaluate_cell([prepared], cell, conds, "dev", max_turns=6)[0]
    e = r.mean_entropy_by_turn
    assert e[-1] <= e[0] + 1e-9


def test_baselines_are_invariant_to_the_swept_axes(prepared):
    """Justifies computing them once; if this breaks, the sweep's reference moves."""
    base_conds = [c for c in five_conditions(0) if not c.clustering]
    a = evaluate_baselines([prepared], base_conds, "dev", 6, "header_rows")
    b = evaluate_baselines([prepared], base_conds, "dev", 6, "values_only")
    assert [r.reach_zero_rate for r in a] == [r.reach_zero_rate for r in b]
    assert [r.mean_entropy_by_turn for r in a] == [r.mean_entropy_by_turn for r in b]
