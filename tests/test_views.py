import numpy as np

from pleasqlarify.llm.client import MockLLMClient
from pleasqlarify.pipeline.project import classical_mds, project_2d
from pleasqlarify.server.views import (
    action_space_view,
    decision_space_view,
    predicted_query_view,
)
from pleasqlarify.session import build_session


def _session(schema, film_db, review_completions):
    return build_session(
        "What was the review of the drama film?",
        schema,
        film_db,
        MockLLMClient(review_completions),
    )


def test_classical_mds_shape_and_determinism():
    d = np.array([[0.0, 1.0, 2.0], [1.0, 0.0, 1.5], [2.0, 1.5, 0.0]])
    a = classical_mds(d)
    b = classical_mds(d)
    assert a.shape == (3, 2)
    assert np.allclose(a, b)  # deterministic


def test_project_2d_identical_outputs_coincide():
    sim = np.ones((3, 3))  # all identical outputs
    coords = project_2d(sim)
    assert np.allclose(coords, coords[0])  # all at the same point


def test_action_space_view_payload(schema, film_db, review_completions):
    s = _session(schema, film_db, review_completions)
    v = action_space_view(s)
    assert len(v["queries"]) == len(s.surviving_ids)
    for q in v["queries"]:
        assert {"id", "x", "y", "cluster_id", "color", "rows", "cols", "sql"} <= q.keys()


def test_decision_space_example_contains_group(schema, film_db, review_completions):
    s = _session(schema, film_db, review_completions)
    v = decision_space_view(s)
    assert v["top_id"] is not None
    for var in v["variables"]:
        if var["example"] is not None:
            group = set(var["example"]["group"])
            example_atoms = {a["index"] for a in var["example"]["atoms"]}
            assert group <= example_atoms  # the example actually contains the variable


def test_predicted_query_determined_flag(schema, film_db, review_completions):
    s = _session(schema, film_db, review_completions)
    v = predicted_query_view(s)
    for f in v["features"]:
        assert (f["state"] == "determined") == (f["prob"] >= 0.999)
