"""A6 aligned to the authors: whole-WHERE atoms, set-op recursion, FROM tables.

AMBROSIA's attachment and scope ambiguities are UNION queries whose readings
differ only in *which branch* carries the filter. Two bugs made those readings
indistinguishable, and both are regression-tested here.
"""

from __future__ import annotations

import sqlite3

import pytest

from pleasqlarify.data.ambrosia import schema_from_sqlite
from pleasqlarify.pipeline.features import _atoms_for, parse_and_qualify


@pytest.fixture
def union_schema(tmp_path):
    path = str(tmp_path / "u.sqlite")
    con = sqlite3.connect(path)
    con.executescript(
        "CREATE TABLE Lounges (name TEXT, hours TEXT);"
        "CREATE TABLE Bars (name TEXT, hours TEXT);"
    )
    con.commit()
    con.close()
    return schema_from_sqlite(path)


def _payloads(sql, schema, **kw) -> set[str]:
    ast = parse_and_qualify(sql, schema)
    assert ast is not None, sql
    return {p for _k, p in _atoms_for(ast, **kw)}


LEFT = 'SELECT name FROM Lounges WHERE hours = "x" UNION SELECT name FROM Bars'
RIGHT = 'SELECT name FROM Lounges UNION SELECT name FROM Bars WHERE hours = "x"'


def test_union_branches_are_both_visited(union_schema):
    """REGRESSION: only the first branch was visited, so half the query vanished."""
    atoms = _payloads(LEFT, union_schema)
    assert any("lounges" in a.lower() for a in atoms)
    assert any("bars" in a.lower() for a in atoms), atoms


def test_the_two_attachment_readings_are_atom_distinguishable(union_schema):
    """REGRESSION: without branch recursion both readings produced identical atoms,
    so no decision variable could ever separate them."""
    left, right = _payloads(LEFT, union_schema), _payloads(RIGHT, union_schema)
    assert left != right
    assert left ^ right, "the readings must differ in at least one atom"


def test_from_tables_are_extracted(union_schema):
    """REGRESSION: sqlglot 30 renamed the arg 'from' -> 'from_', so FROM atoms were
    silently absent from every run."""
    atoms = _payloads("SELECT name FROM Lounges", union_schema)
    assert any(a.startswith("FROM ") for a in atoms), atoms


def test_set_operation_itself_is_an_atom(union_schema):
    assert any(a.startswith("SETOP") for a in _payloads(LEFT, union_schema))
    assert not any(a.startswith("SETOP") for a in _payloads("SELECT name FROM Bars", union_schema))


def test_nesting_depth_is_part_of_the_atom(union_schema):
    """Same column at a different nesting level is a different atom."""
    flat = _payloads("SELECT name FROM Lounges", union_schema)
    nested = _payloads(LEFT, union_schema)
    assert not (flat & nested), (flat, nested)


def test_whole_where_clause_is_one_atom_by_default(union_schema):
    sql = 'SELECT name FROM Lounges WHERE hours = "x" AND name = "y"'
    clause = {a for a in _payloads(sql, union_schema) if a.startswith("WHERE")}
    assert len(clause) == 1, clause
    # the per-predicate granularity remains available as the A6 alternative
    preds = {
        a
        for a in _payloads(sql, union_schema, where_granularity="predicate")
        if a.startswith("WHERE")
    }
    assert len(preds) == 2, preds


def test_boolean_structure_changes_the_where_atom(union_schema):
    """a AND (b OR c) must not collapse to the same atom as (a AND b) OR c."""
    a = _payloads(
        'SELECT name FROM Lounges WHERE hours = "x" AND (name = "y" OR name = "z")',
        union_schema,
    )
    b = _payloads(
        'SELECT name FROM Lounges WHERE (hours = "x" AND name = "y") OR name = "z"',
        union_schema,
    )
    assert {x for x in a if x.startswith("WHERE")} != {x for x in b if x.startswith("WHERE")}
