"""Authors' pool loader, their sample filter, and the config preset (spec 17)."""

from __future__ import annotations

import json

import pytest

from pleasqlarify.authors_config import AUTHORS, OURS_ORIGINAL, get_preset
from pleasqlarify.data.authors_pools import (
    load_authors_pools,
    materialize_db,
    pool_contains_all_golds,
)

DUMP = (
    "CREATE TABLE Lounges (name TEXT, hours TEXT);"
    "CREATE TABLE Bars (name TEXT, hours TEXT);"
    "INSERT INTO Lounges VALUES ('Mixologist','5pm-2am'),('Quiet','noon-8pm');"
    "INSERT INTO Bars VALUES ('Central','5pm-2am');"
)

GOLD_A = 'SELECT name FROM Lounges WHERE hours = "5pm-2am" UNION SELECT name FROM Bars'
GOLD_B = 'SELECT name FROM Lounges UNION SELECT name FROM Bars WHERE hours = "5pm-2am"'


# ------------------------------------------------------------------- preset


def test_authors_preset_pins_every_settled_decision():
    assert AUTHORS.similarity_style == "row_aligned"     # A3/A4
    assert AUTHORS.k_mode == "authors"                   # A5
    assert AUTHORS.where_granularity == "clause"         # A6
    assert AUTHORS.termination == "similarity_one"       # A12
    assert AUTHORS.gold_assignment == "execution"        # A14
    assert AUTHORS.entropy_units == "bits"               # A15


def test_presets_differ_on_every_axis_that_was_realigned():
    for f in ("similarity_style", "k_mode", "where_granularity",
              "termination", "gold_assignment"):
        assert getattr(AUTHORS, f) != getattr(OURS_ORIGINAL, f), f


def test_session_kwargs_are_accepted_by_build_session(film_db, schema, review_completions):
    from pleasqlarify.llm.client import MockLLMClient
    from pleasqlarify.session import build_session

    sess = build_session(
        "What was the review of the drama film?", schema, film_db,
        MockLLMClient(review_completions), **AUTHORS.session_kwargs(),
    )
    assert sess.k_mode == "authors"
    assert sess.termination == "similarity_one"


def test_unknown_preset_raises():
    with pytest.raises(ValueError):
        get_preset("nope")


# ------------------------------------------------------- their sample filter


def test_filter_keeps_a_pool_containing_every_gold():
    pool = [GOLD_A, GOLD_B, "SELECT name FROM Bars"]
    assert pool_contains_all_golds(pool, [GOLD_A, GOLD_B])


def test_filter_rejects_a_pool_missing_one_gold():
    """The paper's numbers are conditioned on this; a pool with one reading is out."""
    assert not pool_contains_all_golds([GOLD_A, "SELECT name FROM Bars"], [GOLD_A, GOLD_B])


def test_filter_is_insensitive_to_formatting_but_not_to_meaning():
    spaced = 'SELECT   name FROM Lounges WHERE hours = "5pm-2am"  UNION SELECT name FROM Bars'
    assert pool_contains_all_golds([spaced], [GOLD_A])
    assert not pool_contains_all_golds([GOLD_B], [GOLD_A])


def test_filter_rejects_empty_golds_and_unparseable_golds():
    assert not pool_contains_all_golds([GOLD_A], [])
    assert not pool_contains_all_golds([GOLD_A], ["this is not sql ((("])


# --------------------------------------------------------------- the loader


@pytest.fixture
def pools_file(tmp_path):
    rows = [
        {   # both golds present -> survives the authors' filter
            "ambig_question": "Provide lounges and bars open 5pm to 2am.",
            "generated_sql": [GOLD_A, GOLD_B, "SELECT name FROM Bars"],
            "ambig_queries": [GOLD_A, GOLD_B],
            "ambig_type": "attachment", "split": "test",
            "db_file": "data/x/lounge_bars.sqlite", "db_dump": DUMP, "domain": "Nightlife",
        },
        {   # only one gold present -> filtered out when required
            "ambig_question": "Another question entirely.",
            "generated_sql": [GOLD_A],
            "ambig_queries": [GOLD_A, GOLD_B],
            "ambig_type": "scope", "split": "test",
            "db_file": "data/x/other.sqlite", "db_dump": DUMP,
        },
        {   # wrong split -> excluded by default
            "ambig_question": "Few-shot example.",
            "generated_sql": [GOLD_A], "ambig_queries": [GOLD_A],
            "ambig_type": "vague", "split": "few_shot_examples",
            "db_file": "data/x/fs.sqlite", "db_dump": DUMP,
        },
    ]
    p = tmp_path / "pools.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows))
    return str(p)


def test_loader_materializes_a_working_database(pools_file, tmp_path):
    samples = list(load_authors_pools(pools_file, cache_dir=str(tmp_path / "dbs")))
    assert samples
    s = samples[0]
    from pleasqlarify.data.execution import run_query

    rt = run_query(s.db_path, "SELECT name FROM Lounges ORDER BY name")
    assert not rt.is_error and rt.n_rows == 2


def test_loader_respects_split_and_carries_the_pool(pools_file, tmp_path):
    samples = list(load_authors_pools(pools_file, cache_dir=str(tmp_path / "dbs")))
    assert {s.ambiguity_type for s in samples} == {"attachment", "scope"}  # no few_shot
    assert all(len(s.generated_sql) >= 1 for s in samples)
    assert all(len(s.gold_queries) == 2 for s in samples)


def test_loader_applies_the_authors_filter_on_request(pools_file, tmp_path):
    kept = list(load_authors_pools(pools_file, cache_dir=str(tmp_path / "d2"),
                                   require_all_golds=True))
    assert [s.ambiguity_type for s in kept] == ["attachment"]


def test_sample_ids_are_unique_per_question(pools_file, tmp_path):
    samples = list(load_authors_pools(pools_file, cache_dir=str(tmp_path / "dbs")))
    assert len({s.sample_id for s in samples}) == len(samples)


def test_materialize_db_is_idempotent(tmp_path):
    a = materialize_db(DUMP, str(tmp_path), "k")
    b = materialize_db(DUMP, str(tmp_path), "k")
    assert a == b


# ------------------------------------------------- malformed dumps (10/300)

MALFORMED = (
    "CREATE TABLE Applicants (\n"
    "    id INTEGER PRIMARY KEY,\n"
    "    email TEXT,\n"
    ");\n"
    "INSERT INTO Applicants (id,email) VALUES (1,'a@b.c');"
)


def test_trailing_comma_in_create_table_is_repaired(tmp_path):
    """10 of the authors' 300 dumps have `col TYPE,\n)` which SQLite rejects."""
    from pleasqlarify.data.execution import run_query

    path = materialize_db(MALFORMED, str(tmp_path), "m")
    rt = run_query(path, "SELECT email FROM Applicants")
    assert not rt.is_error, rt.error
    assert rt.rows == [("a@b.c",)]


def test_repair_never_rewrites_insert_payloads(tmp_path):
    """A string literal containing ',)' must survive the repair untouched."""
    from pleasqlarify.data.authors_pools import repair_dump
    from pleasqlarify.data.execution import run_query

    dump = (
        "CREATE TABLE T (v TEXT);\n"
        "INSERT INTO T (v) VALUES ('weird,)value');"
    )
    assert "weird,)value" in repair_dump(dump)
    path = materialize_db(dump, str(tmp_path), "lit")
    assert run_query(path, "SELECT v FROM T").rows == [("weird,)value",)]
