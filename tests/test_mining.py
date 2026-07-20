"""A8: lift-mined cluster-characteristic itemsets (the authors' feature grouping)."""

from __future__ import annotations

import pytest

from pleasqlarify.model.types import Candidate, Cluster
from pleasqlarify.pipeline.decision_vars import _candidate_groups
from pleasqlarify.pipeline.mining import (
    GAMMA_SIZE_PENALTY,
    MIN_LEN,
    apriori_itemsets,
    mine_cluster_group,
    mine_groups,
    top_itemsets_for_cluster,
)


def _c(cid: str, *atoms: int) -> Candidate:
    return Candidate(id=cid, sql=cid, z=frozenset(atoms))


# ------------------------------------------------------------------- apriori


def test_apriori_respects_support_and_length_and_downward_closure():
    members = [_c("a", 1, 2, 3), _c("b", 1, 2), _c("c", 1, 2), _c("d", 4)]
    found = apriori_itemsets(members, max_len=2, min_support=0.5)
    assert frozenset({1}) in found and frozenset({2}) in found
    assert frozenset({1, 2}) in found          # support 3/4
    assert frozenset({3}) not in found          # support 1/4 < 0.5
    assert all(len(s) <= 2 for s in found)


def test_apriori_can_reach_the_authors_max_length_of_four():
    members = [_c(f"c{i}", 1, 2, 3, 4) for i in range(4)]
    found = apriori_itemsets(members, max_len=4, min_support=0.5)
    assert frozenset({1, 2, 3, 4}) in found


def test_apriori_on_empty_or_degenerate_input():
    assert apriori_itemsets([], 3, 0.1) == []
    assert apriori_itemsets([_c("a")], 3, 0.1) == []


# ----------------------------------------------------------------------- lift


def test_itemsets_are_ranked_by_lift_against_the_rest_of_the_pool():
    """An itemset common inside the cluster and absent outside must rank first."""
    members = [_c("m1", 1, 2), _c("m2", 1, 2), _c("m3", 1, 2)]
    others = [_c("o1", 1, 9), _c("o2", 1, 8)]          # atom 1 is everywhere
    top = top_itemsets_for_cluster(members, others, max_len=2, min_lift=1.0)
    assert top
    best = top[0]
    assert 2 in best.itemset, best          # the discriminative atom is included
    assert best.lift > 1.0


def test_itemsets_below_min_lift_are_dropped():
    members = [_c("m1", 1), _c("m2", 1)]
    others = [_c("o1", 1), _c("o2", 1)]     # atom 1 is not characteristic at all
    assert top_itemsets_for_cluster(members, others, max_len=2, min_lift=1.3) == []


# ------------------------------------------------------- the mined group rule


def test_mined_group_is_multi_atom_because_min_len_is_two():
    """min_len=2 in their code: a mined group is never a single atom."""
    assert MIN_LEN == 2
    members = [_c("m1", 1, 2), _c("m2", 1, 2), _c("m3", 1, 2)]
    others = [_c("o1", 7), _c("o2", 8)]
    groups = mine_cluster_group(members, others)
    assert groups
    assert all(len(g) >= 2 for g in groups)


def test_only_top_one_group_per_cluster_is_kept():
    members = [_c("m1", 1, 2, 3), _c("m2", 1, 2, 3), _c("m3", 1, 2, 3)]
    others = [_c("o1", 9)]
    assert len(mine_cluster_group(members, others)) == 1


def test_no_qualifying_itemset_yields_no_group():
    members = [_c("m1", 1), _c("m2", 2)]    # nothing frequent and multi-atom
    others = [_c("o1", 1), _c("o2", 2)]
    assert mine_cluster_group(members, others) == []


def test_size_penalty_is_the_authors_formula():
    """score contribution = (lift-1) * supp_in * 1/(1 + gamma*(size-1))."""
    assert GAMMA_SIZE_PENALTY == 0.25
    penalty_1 = 1.0 / (1.0 + GAMMA_SIZE_PENALTY * 0)
    penalty_3 = 1.0 / (1.0 + GAMMA_SIZE_PENALTY * 2)
    assert penalty_1 == 1.0
    assert penalty_3 == pytest.approx(1 / 1.5)


# ------------------------------------------------- difference from our gap-fill


def test_mined_group_finds_what_the_common_signature_misses():
    """The point of aligning A8.

    Atoms {1,2} characterise 3 of 4 cluster members, but member m4 lacks them, so
    the intersection-based signature collapses to {} and proposes nothing.
    """
    members = [_c("m1", 1, 2), _c("m2", 1, 2), _c("m3", 1, 2), _c("m4", 5)]
    others = [_c("o1", 7), _c("o2", 8)]

    signature = _candidate_groups(members, "grouped", others)
    assert not any(len(g) > 1 for g in signature), "signature should find no group here"

    mined = _candidate_groups(members, "mined", others)
    assert any(g == frozenset({1, 2}) for g in mined), mined


def test_mined_mode_still_includes_every_single_atom():
    members = [_c("m1", 1, 2), _c("m2", 1, 2)]
    groups = _candidate_groups(members, "mined", [_c("o", 9)])
    assert frozenset({1}) in groups and frozenset({2}) in groups


def test_mine_groups_deduplicates_across_clusters():
    survivors = [_c("a", 1, 2), _c("b", 1, 2), _c("c", 1, 2), _c("d", 1, 2)]
    intents = [
        Cluster(id=0, member_ids=["a", "b"], representative_id="a"),
        Cluster(id=1, member_ids=["c", "d"], representative_id="c"),
    ]
    groups = mine_groups(survivors, intents)
    assert len(groups) == len(set(groups))


def test_a_mined_group_adds_no_cluster_level_partition_beyond_single_atoms():
    """Why Feature Grouping is inert in our architecture (spec 17, A8e/A10).

    Our decision variables partition *intents* (one per cluster), and a group that
    characterises cluster c induces the partition {c} — which some single atom in c
    already induces. The dedup on partitions then drops the group, so the Feature
    Grouping condition collapses onto the Atomic one no matter how well the mining
    works. The authors avoid this because their variables split *candidates* by the
    conjunction mask (`split_mode="mask"`), where a 3-atom group and a 1-atom group
    filter the action space differently even with the same cluster partition.
    """
    from pleasqlarify.model.types import FeatureVocabulary
    from pleasqlarify.pipeline.decision_vars import build_decision_variables

    members = [_c("m1", 1, 2, 3), _c("m2", 1, 2, 3)]
    others = [_c("o1", 9), _c("o2", 9)]
    survivors = members + others
    intents = [
        Cluster(id=0, member_ids=["m1", "m2"], representative_id="m1"),
        Cluster(id=1, member_ids=["o1", "o2"], representative_id="o1"),
    ]
    # mining does find a strong multi-atom group for cluster 0 ...
    mined = mine_cluster_group(members, others)
    assert mined and len(mined[0]) >= 2

    vocab = FeatureVocabulary()
    for a in range(10):
        vocab.intern("ATOM", f"a{a}")
    variables = build_decision_variables(survivors, intents, vocab, mode="mined")
    # ... yet no multi-atom variable survives: its partition duplicates a single's
    assert not any(len(v.group) > 1 for v in variables), [sorted(v.group) for v in variables]
