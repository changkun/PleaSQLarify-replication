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


def test_paths_with_uri_delimiters_open_the_right_database(tmp_path):
    """REGRESSION: run_query builds a `file:...` URI, so a '#' in the path was read
    as a URI fragment and silently opened a different, empty database."""
    import sqlite3

    from pleasqlarify.data.execution import run_query

    for name in ("plain.sqlite", "has#hash.sqlite", "has?query.sqlite"):
        path = str(tmp_path / name)
        con = sqlite3.connect(path)
        con.executescript("CREATE TABLE T (v TEXT); INSERT INTO T VALUES ('ok');")
        con.commit()
        con.close()

        rt = run_query(path, "SELECT v FROM T")
        assert not rt.is_error, (name, rt.error)
        assert rt.rows == [("ok",)], name
