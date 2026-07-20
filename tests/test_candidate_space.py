"""A10: candidate-level decision variables (the authors' architecture)."""

from __future__ import annotations

import numpy as np
import pytest

from pleasqlarify.candidate_space import (
    CandidateSession,
    build_candidate_variables,
    frequency_prior,
)
from pleasqlarify.model.types import Candidate, Cluster, FeatureVocabulary
from pleasqlarify.pipeline.ranking import information_gain


def _c(cid: str, atoms, gen_count: int = 1) -> Candidate:
    return Candidate(id=cid, sql=cid, z=frozenset(atoms), gen_count=gen_count)


def _vocab(n: int = 12) -> FeatureVocabulary:
    v = FeatureVocabulary()
    for i in range(n):
        v.intern("ATOM", f"a{i}")
    return v


def _index(cands):
    return {c.id: i for i, c in enumerate(cands)}


# ------------------------------------------------------------------- prior


def test_belief_is_the_generation_frequency_prior():
    """Their CandidateSQL.prob is normalized_count, not a uniform over clusters."""
    cands = [_c("a", [1], gen_count=3), _c("b", [2], gen_count=1)]
    belief = frequency_prior(cands, _index(cands))
    assert belief == pytest.approx({0: 0.75, 1: 0.25})
    assert sum(belief.values()) == pytest.approx(1.0)


# --------------------------------------------------- the point of this module


def test_a_group_and_an_atom_with_the_same_cluster_partition_are_distinct_variables():
    """Why A10 was the blocker.

    Under cluster-partition variables, a mined group characterising cluster c and a
    single atom of c induce the same partition {c} and the group is deduped away.
    Splitting *candidates* keeps them distinct, because they select different
    candidate sets.
    """
    cands = [
        _c("m1", [1, 2]), _c("m2", [1, 2]), _c("m3", [1]),   # cluster 0
        _c("o1", [9]), _c("o2", [9]),                        # cluster 1
    ]
    idx = _index(cands)
    belief = frequency_prior(cands, idx)
    intents = [
        Cluster(id=0, member_ids=["m1", "m2", "m3"], representative_id="m1"),
        Cluster(id=1, member_ids=["o1", "o2"], representative_id="o1"),
    ]
    variables = build_candidate_variables(
        cands, intents, _vocab(), idx, belief, group_split="mask"
    )
    positives = {v.contains_cluster_ids for v in variables}
    # atom 1 selects {m1,m2,m3}; the mined group {1,2} selects only {m1,m2}
    assert frozenset({0, 1, 2}) in positives, positives
    assert frozenset({0, 1}) in positives, positives


def test_cluster_split_mode_uses_cluster_membership_not_the_mask():
    cands = [_c("m1", [1, 2]), _c("m2", [1, 2]), _c("m3", [1]), _c("o1", [9])]
    idx = _index(cands)
    belief = frequency_prior(cands, idx)
    intents = [
        Cluster(id=0, member_ids=["m1", "m2", "m3"], representative_id="m1"),
        Cluster(id=1, member_ids=["o1"], representative_id="o1"),
    ]
    by_split = {}
    for mode in ("mask", "cluster"):
        vs = build_candidate_variables(
            cands, intents, _vocab(), idx, belief,
            include_atomic=False, group_split=mode,
        )
        by_split[mode] = {v.contains_cluster_ids for v in vs}
    # cluster mode selects all three members; mask mode only those carrying {1,2}
    assert frozenset({0, 1, 2}) in by_split["cluster"]
    assert frozenset({0, 1}) in by_split["mask"]


# ------------------------------------------------------------ variable hygiene


def test_degenerate_and_tiny_splits_are_rejected():
    cands = [_c(f"c{i}", [1]) for i in range(10)]     # atom 1 in every candidate
    idx = _index(cands)
    belief = frequency_prior(cands, idx)
    vs = build_candidate_variables(cands, [], _vocab(), idx, belief)
    assert vs == []          # no split at all

    # a 1-in-100 split falls below min_bin_frac = 0.02
    cands = [_c("special", [1])] + [_c(f"c{i}", [2]) for i in range(99)]
    idx = _index(cands)
    belief = frequency_prior(cands, idx)
    vs = build_candidate_variables(cands, [], _vocab(), idx, belief)
    assert all(len(v.contains_cluster_ids) > 1 for v in vs), [
        sorted(v.contains_cluster_ids) for v in vs
    ]


def test_information_gain_over_candidate_belief_matches_their_eig():
    """Our IG is generic over the belief keys, so it *is* their eig(var, cands)."""
    cands = [_c("a", [1]), _c("b", [1]), _c("c", [2]), _c("d", [2])]
    idx = _index(cands)
    belief = frequency_prior(cands, idx)
    vs = build_candidate_variables(cands, [], _vocab(), idx, belief)
    assert vs
    # a perfectly balanced binary split of a uniform belief yields exactly 1 bit
    assert max(information_gain(belief, v) for v in vs) == pytest.approx(1.0)


# ---------------------------------------------------------------- the session


def _sim(n: int, blocks) -> np.ndarray:
    s = np.eye(n)
    for block in blocks:
        for i in block:
            for j in block:
                s[i, j] = 1.0
    return s


def test_session_narrows_and_terminates_when_survivors_are_identical():
    cands = [_c("a", [1, 3]), _c("b", [1, 4]), _c("c", [2, 5]), _c("d", [2, 6])]
    sim = _sim(4, [(0, 1), (2, 3)])
    sess = CandidateSession(cands, sim, _vocab(), group_split="mask")
    assert not sess.terminated
    v = sess.ranked[0]
    before = len(sess.surviving_ids)
    sess.answer(v.id, True)
    assert len(sess.surviving_ids) < before
    # survivors now functionally identical -> their sim1 stop fires
    assert sess.terminated


def test_session_answer_keeps_only_the_chosen_branch():
    cands = [_c("a", [1]), _c("b", [1]), _c("c", [2]), _c("d", [2])]
    sess = CandidateSession(cands, np.eye(4), _vocab(), group_split=None)
    v = next(v for v in sess.variables if len(v.contains_cluster_ids) == 2)
    keep = {cands[i].id for i in v.contains_cluster_ids}
    sess.answer(v.id, True)
    assert set(sess.surviving_ids) == keep


def test_unknown_variable_id_raises():
    sess = CandidateSession([_c("a", [1]), _c("b", [2])], np.eye(2), _vocab())
    with pytest.raises(KeyError):
        sess.answer("nope", True)


def test_authors_preset_selects_the_candidate_variable_space():
    from pleasqlarify.authors_config import AUTHORS, OURS_ORIGINAL

    assert AUTHORS.variable_space == "candidate"     # A10
    assert OURS_ORIGINAL.variable_space == "cluster"
