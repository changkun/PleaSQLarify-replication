"""Guards for the grouped-vs-atomic ablation and IG/filter consistency.

These target the paper's headline grouping ablation and a flagged design
assumption (spec 06, A8a: representative-based partition), so a future change that
makes grouping inert or breaks convergence is caught.
"""

from __future__ import annotations

from pleasqlarify.model.types import Candidate, Cluster, FeatureVocabulary
from pleasqlarify.pipeline.decision_vars import build_decision_variables
from pleasqlarify.pipeline.repair_loop import filter_action_space


def _vocab(n):
    v = FeatureVocabulary()
    for k in range(n):
        v.intern("X", f"atom{k}")
    return v


def test_grouping_captures_interaction_neglect():
    # atoms 0 and 1 are each globally common (lift 1 alone), but the PAIR {0,1}
    # is unique to cluster 0. Only grouped mode can isolate cluster 0.
    A = [
        Candidate("c0", "", z=frozenset({0, 1})),
        Candidate("c1", "", z=frozenset({0, 1})),
        Candidate("c2", "", z=frozenset({0, 2})),
        Candidate("c3", "", z=frozenset({1, 3})),
    ]
    intents = [Cluster(0, ["c0", "c1"], "c0"), Cluster(1, ["c2"], "c2"), Cluster(2, ["c3"], "c3")]
    v = _vocab(4)

    atomic = build_decision_variables(A, intents, v, mode="atomic")
    grouped = build_decision_variables(A, intents, v, mode="grouped")

    # no single atom isolates cluster 0 alone...
    assert all(dv.contains_cluster_ids != frozenset({0}) for dv in atomic)
    # ...but the grouped {0,1} variable does.
    isolating = [dv for dv in grouped if dv.contains_cluster_ids == frozenset({0})]
    assert isolating and any(dv.group == frozenset({0, 1}) for dv in isolating)


def test_filter_consistent_with_value_of_for_grouped_signature():
    # grouped multi-atom variables come from the cluster's common signature, so
    # every member carries them -> per-candidate filter agrees with value_of.
    A = [
        Candidate("c0", "", z=frozenset({0, 1})),
        Candidate("c1", "", z=frozenset({0, 1})),
        Candidate("c2", "", z=frozenset({0, 2})),
        Candidate("c3", "", z=frozenset({1, 3})),
    ]
    intents = [Cluster(0, ["c0", "c1"], "c0"), Cluster(1, ["c2"], "c2"), Cluster(2, ["c3"], "c3")]
    grouped = build_decision_variables(A, intents, _vocab(4), mode="grouped")
    pair = next(dv for dv in grouped if dv.group == frozenset({0, 1}))
    kept = filter_action_space(A, pair, True)
    # answering Yes keeps exactly cluster 0's members (c0, c1)
    assert {c.id for c in kept} == {"c0", "c1"}
