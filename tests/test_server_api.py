import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from pleasqlarify.server.app import create_app  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PLEASQL_LOG_DIR", str(tmp_path / "sessions"))
    # rebuild app so it picks up the patched log dir
    import importlib

    import pleasqlarify.server.app as appmod

    importlib.reload(appmod)
    return TestClient(appmod.create_app())


def test_demo_session_and_views(client):
    r = client.post("/demo")
    assert r.status_code == 200
    state = r.json()
    sid = state["session_id"]
    assert state["n_candidates"] >= 2
    assert state["action_space"]["queries"]
    assert state["decision_space"]["variables"]
    assert "features" in state["predicted_query"]

    # linked GET views are consistent with the start state
    a = client.get(f"/session/{sid}/action_space").json()
    assert len(a["queries"]) == state["n_candidates"]


def test_answer_shrinks_and_undo_restores(client):
    state = client.post("/demo").json()
    sid = state["session_id"]
    top = state["decision_space"]["top_id"]
    n0 = state["n_candidates"]

    after = client.post(f"/session/{sid}/answer", json={"variable_id": top, "value": True}).json()
    assert after["n_candidates"] <= n0
    assert after["turn"] == 1

    back = client.post(f"/session/{sid}/undo").json()
    assert back["n_candidates"] == n0
    assert back["turn"] == 0


def test_unknown_session_404(client):
    assert client.get("/session/nope/action_space").status_code == 404


def test_start_with_explicit_completions(client, film_db):
    from pleasqlarify.data.demo import DEMO_COMPLETIONS

    r = client.post(
        "/session",
        json={
            "utterance": "What was the review of the drama film?",
            "db_path": film_db,
            "completions": DEMO_COMPLETIONS,
        },
    )
    assert r.status_code == 200
    assert r.json()["n_candidates"] >= 2
