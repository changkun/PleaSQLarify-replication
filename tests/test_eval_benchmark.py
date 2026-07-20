import pytest

from pleasqlarify.eval.conditions import five_conditions
from pleasqlarify.eval.run_benchmark import (
    EvalSample,
    aggregate,
    mean_convergence_turn,
    run_benchmark,
)
from pleasqlarify.llm.client import MockLLMClient

GOLD_OPINION = "SELECT Opinion FROM Reviews WHERE FilmId IN (SELECT id FROM Film WHERE Genre='Drama')"
GOLD_AUDIENCE = "SELECT AudienceReviews FROM Reviews WHERE FilmId IN (SELECT id FROM Film WHERE Genre='Drama')"


@pytest.fixture
def eval_sample(schema, film_db, review_completions):
    return EvalSample(
        sample_id="review-1",
        ambiguity_type="vague",
        utterance="What was the review of the drama film?",
        schema=schema,
        db_path=film_db,
        gold_sqls=[GOLD_OPINION, GOLD_AUDIENCE],
        client=MockLLMClient(review_completions),
    )


def test_benchmark_runs_all_conditions(eval_sample):
    rows = run_benchmark([eval_sample], max_turns=8)
    conds = {r.condition for r in rows}
    assert conds == {c.name for c in five_conditions()}
    # every run produces a full turn trajectory 0..8
    assert max(r.turn for r in rows) == 8


def test_initial_uncertainty_then_convergence(eval_sample):
    rows = run_benchmark([eval_sample], max_turns=8)
    turn0 = [r.entropy for r in rows if r.turn == 0]
    assert max(turn0) > 0.0  # ambiguity present at the start

    # 'ours' (clustering + grouped) converges to zero residual entropy
    ours = "Clustering + EIG + Feature Grouping"
    final_ours = [r.entropy for r in rows if r.condition == ours and r.turn == 8]
    assert max(final_ours) == pytest.approx(0.0, abs=1e-9)


def test_clustering_converges_no_slower_than_baseline(eval_sample):
    rows = run_benchmark([eval_sample], max_turns=8)
    ours = mean_convergence_turn(rows, "Clustering + EIG + Feature Grouping")
    random_base = mean_convergence_turn(rows, "Baseline Random + Atomic")
    assert ours <= random_base  # directional Figure-5 claim
    assert ours <= 5  # grouped collapses within a few turns (paper: 3-5)


def test_aggregate_has_cis(eval_sample):
    rows = run_benchmark([eval_sample], max_turns=4)
    agg = aggregate(rows)
    key = ("Clustering + EIG + Feature Grouping", "vague", 0)
    assert key in agg
    med, lo, hi = agg[key]["entropy"]
    assert lo <= med <= hi
