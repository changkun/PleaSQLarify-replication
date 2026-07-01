import math

from pleasqlarify.model.types import Candidate, Cluster, FeatureVocabulary
from pleasqlarify.pipeline.decision_vars import (
    atom_probabilities,
    build_decision_variables,
    cooccurrence,
    lift,
)

# atoms: 0 = SELECT Opinion, 1 = SELECT AudienceReviews, 2 = FROM Reviews (global)


def _fixture():
    A = [
        Candidate("c0", "", z=frozenset({0, 2})),
        Candidate("c1", "", z=frozenset({0, 2})),
        Candidate("c2", "", z=frozenset({1, 2})),
        Candidate("c3", "", z=frozenset({1, 2})),
    ]
    intents = [
        Cluster(0, ["c0", "c1"], "c0"),
        Cluster(1, ["c2", "c3"], "c2"),
    ]
    return A, intents


def test_lift_matches_eq4_5():
    A, intents = _fixture()
    cluster0 = [A[0], A[1]]
    # p_in({0}) = 2/2 = 1 ; p_all = 2/4 = 0.5 ; lift = 2
    assert lift(frozenset({0}), cluster0, A) == 2.0
    # global feature {2}: lift = 1 -> not characteristic
    assert lift(frozenset({2}), cluster0, A) == 1.0


def test_cooccurrence_matches_eq6():
    A, _ = _fixture()
    # among candidates containing atom 0 (c0,c1), all contain 2 -> 1.0
    assert cooccurrence(frozenset({2}), frozenset({0}), A) == 1.0
    # none containing 0 also contain 1 -> 0.0
    assert cooccurrence(frozenset({1}), frozenset({0}), A) == 0.0


def test_build_drops_global_and_splits():
    A, intents = _fixture()
    vocab = FeatureVocabulary()
    for _ in range(3):
        pass
    vocab.intern("SELECT_COL", "SELECT Reviews.Opinion")
    vocab.intern("SELECT_COL", "SELECT Reviews.AudienceReviews")
    vocab.intern("FROM_TABLE", "FROM Reviews")
    dvs = build_decision_variables(A, intents, vocab, mode="grouped")
    # the global feature (atom 2) must not appear as a decision variable
    assert all(2 not in dv.group for dv in dvs)
    # every decision variable induces a real split of the two clusters
    for dv in dvs:
        assert 0 < len(dv.contains_cluster_ids) < len(intents)


def test_atom_probabilities():
    A, _ = _fixture()
    probs = atom_probabilities(A, frozenset())  # no selection -> marginal
    assert probs[2] == 1.0  # global atom present in all
    assert math.isclose(probs[0], 0.5)
