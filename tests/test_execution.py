from pleasqlarify.data.execution import run_query


def test_run_query_basic(film_db):
    rt = run_query(film_db, "SELECT Title FROM Film WHERE Genre='Drama'")
    assert rt.error is None
    assert rt.columns == ["Title"]
    assert rt.n_rows == 2


def test_error_is_captured_not_raised(film_db):
    rt = run_query(film_db, "SELECT nope FROM Nope")
    assert rt.is_error
    assert rt.n_rows == 0


def test_unordered_result_is_canonically_sorted(film_db):
    # No ORDER BY -> deterministic sort so logically-equal queries match (F3).
    a = run_query(film_db, "SELECT Title FROM Film")
    b = run_query(film_db, "SELECT Title FROM Film")
    assert a.rows == b.rows
    assert a.rows == sorted(a.rows)
