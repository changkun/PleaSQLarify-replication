import numpy as np

from pleasqlarify.model.types import Candidate, ResultTable
from pleasqlarify.pipeline.cluster import cluster_candidates
from pleasqlarify.pipeline.embed import (
    DeterministicEmbedder,
    serialize_result,
    similarity_matrix,
)


def _cand(cid, cols, rows):
    return Candidate(cid, f"SQL {cid}", result=ResultTable(columns=cols, rows=rows))


def test_serialize_error_and_empty_share_sentinel():
    err = serialize_result(ResultTable(error="boom"))
    empty = serialize_result(ResultTable(columns=["x"], rows=[]))
    assert err == empty  # A4: degenerate outputs share a sentinel


def test_similarity_identical_outputs_is_one():
    a = _cand("a", ["Opinion"], [("A masterpiece.",)])
    b = _cand("b", ["Opinion"], [("A masterpiece.",)])
    sim = similarity_matrix([a, b], DeterministicEmbedder())
    assert sim[0, 1] == 1.0
    assert np.allclose(np.diag(sim), 1.0)


def test_gold_intents_separate_into_clusters():
    # Two distinct outputs -> two clusters (core property of spec 04).
    opinion = [_cand(f"o{i}", ["Opinion"], [("A masterpiece.",), ("Terrific acting.",)]) for i in range(2)]
    audience = [_cand(f"a{i}", ["AudienceReviews"], [("Five stars!",), ("Audience loved it!",)]) for i in range(2)]
    cands = opinion + audience
    sim = similarity_matrix(cands, DeterministicEmbedder())
    intents = cluster_candidates(cands, sim, threshold=0.1)
    assert len(intents) == 2
    # members of each intent share a cluster id
    ids = {c.id: c.cluster_id for c in cands}
    assert ids["o0"] == ids["o1"]
    assert ids["a0"] == ids["a1"]
    assert ids["o0"] != ids["a0"]


def test_fixed_k_mode():
    cands = [_cand(f"c{i}", ["x"], [(i,)]) for i in range(5)]
    sim = similarity_matrix(cands, DeterministicEmbedder())
    intents = cluster_candidates(cands, sim, k=2)
    assert len(intents) == 2
