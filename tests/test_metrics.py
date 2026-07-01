import math

import numpy as np

from pleasqlarify.eval.metrics import (
    bootstrap_ci,
    gold_label_entropy,
    mean_pairwise_similarity,
)


def test_gold_label_entropy():
    # two survivors, one per gold label -> maximal uncertainty ln 2
    assert math.isclose(gold_label_entropy(["a", "b"], {"a": 0, "b": 1}), math.log(2))
    # both same label -> zero uncertainty
    assert gold_label_entropy(["a", "b"], {"a": 0, "b": 0}) == 0.0
    assert gold_label_entropy([], {}) == 0.0


def test_mean_pairwise_similarity():
    sim = np.array([[1.0, 0.2, 0.2], [0.2, 1.0, 0.2], [0.2, 0.2, 1.0]])
    assert math.isclose(mean_pairwise_similarity([0, 1, 2], sim), 0.2)
    assert mean_pairwise_similarity([0], sim) == 1.0  # single survivor homogeneous


def test_bootstrap_ci_brackets_median():
    med, lo, hi = bootstrap_ci([0.0, 0.5, 1.0, 0.5, 0.5], n_boot=1000, seed=1)
    assert lo <= med <= hi
    assert math.isclose(med, 0.5)
