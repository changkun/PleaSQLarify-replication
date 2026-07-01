from pleasqlarify.llm.client import MockLLMClient
from pleasqlarify.session import build_session


def _build(schema, film_db, review_completions, **kw):
    return build_session(
        "What was the review of the drama film?",
        schema,
        film_db,
        MockLLMClient(review_completions),
        **kw,
    )


def test_generation_collapses_and_drops(schema, film_db, review_completions):
    s = _build(schema, film_db, review_completions)
    sqls = [c.sql for c in s.candidates]
    # the unparseable "SELECT SELECT FROM WHERE" is dropped
    assert all("SELECT SELECT" not in q for q in sqls)
    # the byte-identical Opinion subquery was sampled twice -> gen_count 2
    dup = [c for c in s.candidates if c.gen_count == 2]
    assert dup, "identical raw generations should collapse with gen_count"


def test_initial_intents_separate(schema, film_db, review_completions):
    s = _build(schema, film_db, review_completions)
    # Opinion / AudienceReviews / CriticName produce three distinct outputs
    assert len(s.intents) >= 2


def test_loop_converges_and_is_monotonic(schema, film_db, review_completions):
    s = _build(schema, film_db, review_completions)
    # simulated user wants the *critic Opinion* interpretation
    target = next(c for c in s.candidates if "Opinion" in c.sql and "Audience" not in c.sql)

    prev = len(s.surviving_ids)
    turns = 0
    while not s.terminated and turns < 20:
        v = s.next_variable()
        assert v is not None
        answer = v.group <= target.z  # oracle (spec 10, A13)
        s.answer(v.id, answer)
        assert len(s.surviving_ids) <= prev  # monotonic non-increasing
        prev = len(s.surviving_ids)
        turns += 1

    assert s.terminated
    assert turns < 20
    # converged onto the intended interpretation
    final = s.final_query()
    assert final is not None
    assert "Opinion" in final.sql and "Audience" not in final.sql


def test_undo_restores(schema, film_db, review_completions):
    s = _build(schema, film_db, review_completions)
    before = list(s.surviving_ids)
    v = s.next_variable()
    s.answer(v.id, True)
    s.undo()
    assert s.surviving_ids == before
    assert s.turn == 0


def test_atomic_mode_runs(schema, film_db, review_completions):
    s = _build(schema, film_db, review_completions, mode="atomic")
    v = s.next_variable()
    assert v is not None
    assert len(v.group) == 1  # atomic variant uses single-atom variables
