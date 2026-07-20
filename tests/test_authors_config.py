"""A5 (k heuristic) and A12 (similarity-one stop) as the authors implement them."""

from __future__ import annotations

import numpy as np
import pytest

from pleasqlarify.model.types import Candidate, Cluster, DecisionVariable
from pleasqlarify.pipeline.cluster import MAX_K, authors_k
from pleasqlarify.pipeline.repair_loop import is_terminated


# ------------------------------------------------------------------ A5: k rule


@pytest.mark.parametrize(
    "n,expected",
    [
        (1, 2),    # round(0.1)=0 -> `or 2` -> 2
        (5, 2),    # round(0.5)=0 -> 2
        (10, 2),   # round(1)=1 -> max(2, 1) -> 2
        (25, 2),   # round(2.5)=2 (banker's rounding in Python) -> 2
        (30, 3),
        (40, 4),
        (95, 4),   # clamped by max_K, incl. the authors' ~95-candidate pools
        (1000, 4),
    ],
)
def test_authors_k_matches_the_clamped_size_heuristic(n, expected):
    """k = max(2, min(max_K, round(n/10) or 2)) — verbatim from their run_eval."""
    assert authors_k(n) == expected


def test_authors_k_is_bounded_for_every_pool_size():
    assert all(2 <= authors_k(n) <= MAX_K for n in range(0, 500))


# --------------------------------------------------- A12: stop at similarity 1


def _var(ig: float) -> DecisionVariable:
    return DecisionVariable(id="v0", group=frozenset({0}), label="v", ig=ig)


def _clusters(n: int):
    return [Cluster(id=i, member_ids=[f"c{i}"], representative_id=f"c{i}") for i in range(n)]


def test_similarity_one_stops_only_when_survivors_are_functionally_identical():
    informative = [_var(0.5)]
    assert is_terminated(_clusters(2), informative, rule="similarity_one", mean_similarity=1.0)
    assert not is_terminated(
        _clusters(2), informative, rule="similarity_one", mean_similarity=0.97
    )


def test_similarity_one_keeps_going_inside_a_single_over_merged_cluster():
    """The key difference from our earlier A12: one cluster is not enough to stop."""
    one_cluster = _clusters(1)
    informative = [_var(0.5)]
    # our original rule stops on the cluster count alone ...
    assert is_terminated(one_cluster, informative, rule="cluster_or_uninformative")
    # ... the authors' rule keeps asking while the survivors still differ.
    assert not is_terminated(
        one_cluster, informative, rule="similarity_one", mean_similarity=0.8
    )


def test_similarity_one_still_stops_when_nothing_is_informative():
    assert is_terminated(_clusters(3), [_var(0.0)], rule="similarity_one", mean_similarity=0.2)


def test_similarity_one_tolerates_float_error_just_below_one():
    assert is_terminated(
        _clusters(2), [_var(0.5)], rule="similarity_one", mean_similarity=1.0 - 1e-12
    )


# ------------------------------------------------------- wired into a Session


def test_session_k_mode_authors_recomputes_k_from_the_surviving_pool(film_db, schema,
                                                                     review_completions):
    from pleasqlarify.llm.client import MockLLMClient
    from pleasqlarify.session import build_session

    sess = build_session(
        "What was the review of the drama film?", schema, film_db,
        MockLLMClient(review_completions), clustering=True, k_mode="authors",
    )
    # small fixture pool -> k clamps to the floor of 2
    assert len(sess.intents) == min(2, len(sess.candidates))
    assert sess.k_mode == "authors"


def test_session_similarity_one_termination_is_selectable(film_db, schema,
                                                          review_completions):
    from pleasqlarify.llm.client import MockLLMClient
    from pleasqlarify.session import build_session

    sess = build_session(
        "What was the review of the drama film?", schema, film_db,
        MockLLMClient(review_completions), clustering=True,
        k_mode="authors", termination="similarity_one",
    )
    # a pool with functionally distinct outputs must not be considered finished
    assert not sess.terminated
