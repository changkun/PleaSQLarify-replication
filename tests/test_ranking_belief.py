import math

from pleasqlarify.model.types import DecisionVariable
from pleasqlarify.pipeline.belief import condition, entropy, uniform_belief
from pleasqlarify.pipeline.ranking import information_gain, best_variable
from pleasqlarify.model.types import Cluster


def _dv(contains):
    return DecisionVariable(
        id="z", group=frozenset({0}), label="z", contains_cluster_ids=frozenset(contains)
    )


def test_entropy_uniform_two():
    b = {0: 0.5, 1: 0.5}
    assert math.isclose(entropy(b), math.log(2))


def test_perfect_split_ig_equals_prior_entropy():
    b = {0: 0.5, 1: 0.5}
    dv = _dv({0})  # splits the two clusters perfectly
    assert math.isclose(information_gain(b, dv), math.log(2))


def test_constant_variable_zero_ig():
    b = {0: 0.5, 1: 0.5}
    dv = _dv({0, 1})  # contains both clusters -> no split
    assert math.isclose(information_gain(b, dv), 0.0, abs_tol=1e-12)


def test_condition_renormalizes():
    b = {0: 0.25, 1: 0.25, 2: 0.5}
    dv = _dv({0, 1})
    post = condition(b, dv, True)
    assert set(post) == {0, 1}
    assert math.isclose(sum(post.values()), 1.0)
    assert math.isclose(post[0], 0.5)


def test_balanced_split_beats_lopsided():
    b = {0: 0.25, 1: 0.25, 2: 0.25, 3: 0.25}
    balanced = _dv({0, 1})  # 50/50
    lopsided = _dv({0})  # 25/75
    assert information_gain(b, balanced) > information_gain(b, lopsided)


def test_best_variable_picks_argmax():
    b = {0: 0.25, 1: 0.25, 2: 0.25, 3: 0.25}
    balanced = _dv({0, 1})
    lopsided = _dv({0})
    lopsided.id = "z2"
    assert best_variable(b, [lopsided, balanced]).id == balanced.id


def test_uniform_belief():
    intents = [Cluster(0, ["a"], "a"), Cluster(1, ["b"], "b")]
    b = uniform_belief(intents)
    assert b == {0: 0.5, 1: 0.5}
