"""End-to-end narrative: generation -> repair loop -> backend -> evaluation.

Ties the whole replication together against the offline demo, with no network.
"""

from __future__ import annotations

import pytest

from pleasqlarify.data.ambrosia import schema_from_sqlite
from pleasqlarify.data.demo import DEMO_COMPLETIONS, DEMO_UTTERANCE, build_demo_db
from pleasqlarify.data.execution import run_query
from pleasqlarify.eval.run_benchmark import EvalSample, mean_convergence_turn, run_benchmark
from pleasqlarify.llm.client import MockLLMClient
from pleasqlarify.session import build_session


@pytest.fixture
def demo(tmp_path):
    path = str(tmp_path / "demo.sqlite")
    build_demo_db(path)
    return path, schema_from_sqlite(path)


def test_algorithm_converges_and_output_is_faithful(demo):
    db_path, schema = demo
    s = build_session(DEMO_UTTERANCE, schema, db_path, MockLLMClient(DEMO_COMPLETIONS))

    # user wants the audience-reviews interpretation
    target = next(c for c in s.candidates if "AudienceReviews" in c.sql)
    turns = 0
    while not s.terminated and turns < 20:
        v = s.next_variable()
        s.answer(v.id, v.group <= target.z)
        turns += 1

    final = s.final_query()
    assert final is not None and "AudienceReviews" in final.sql
    # predicted output equals actually executing the chosen query
    predicted = s.predicted_output()
    fresh = run_query(db_path, final.sql)
    assert predicted.columns == fresh.columns
    assert predicted.rows == fresh.rows


def test_backend_drives_to_termination(demo):
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from pleasqlarify.server.app import create_app

    client = TestClient(create_app())
    state = client.post("/demo").json()
    sid = state["session_id"]

    guard = 0
    while not state["terminated"] and guard < 20:
        top = state["decision_space"]["top_id"]
        assert top is not None
        state = client.post(f"/session/{sid}/answer", json={"variable_id": top, "value": True}).json()
        guard += 1

    assert state["terminated"]
    assert state["predicted_query"]["final_sql"]


def test_evaluation_reproduces_directional_result(demo):
    db_path, schema = demo
    gold = [DEMO_COMPLETIONS[0], DEMO_COMPLETIONS[3]]  # Opinion vs AudienceReviews
    sample = EvalSample(
        "demo", "vague", DEMO_UTTERANCE, schema, db_path, gold,
        MockLLMClient(DEMO_COMPLETIONS),
    )
    rows = run_benchmark([sample], max_turns=8)
    ours = mean_convergence_turn(rows, "Clustering + EIG + Feature Grouping")
    base = mean_convergence_turn(rows, "Baseline Random + Atomic")
    # clustering-based repair resolves uncertainty no slower than the baseline
    assert ours <= base
