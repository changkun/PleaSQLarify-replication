"""Deterministic SQL execution harness (spec 01).

Executes a query against a per-sample SQLite database and returns a
``ResultTable``. Errors are captured, not raised. Result rows are canonically
ordered when the query has no explicit ORDER BY so that two logically-equal
queries serialize identically downstream (spec 01, assumption F3; spec 04, A3).
"""

from __future__ import annotations

import re
import sqlite3
from urllib.parse import quote
from contextlib import closing

from ..model.types import ResultTable

_ORDER_BY_RE = re.compile(r"\border\s+by\b", re.IGNORECASE)


def _canonical_sort_key(row: tuple):
    # None sorts before everything; otherwise compare by (type-name, str) so mixed
    # types never raise and ordering is stable and deterministic.
    return tuple((v is None, type(v).__name__, str(v)) for v in row)


def run_query(db_path: str, sql: str, timeout_s: float = 5.0) -> ResultTable:
    """Execute ``sql`` against the SQLite database at ``db_path`` (read-only)."""
    try:
        # Read-only connection; per-statement interrupt via progress handler timeout
        # is overkill for the tiny AMBROSIA DBs, so rely on the busy timeout only.
        # The path goes into a URI, so '#' and '?' must be percent-encoded or
        # SQLite reads them as fragment/query delimiters and silently opens a
        # *different* (empty) database. Leave '/' intact.
        conn = sqlite3.connect(
            f"file:{quote(db_path, safe='/')}?mode=ro", uri=True, timeout=timeout_s
        )
    except sqlite3.Error as exc:  # pragma: no cover - connection failure is rare
        return ResultTable(error=f"connect: {exc}")

    with closing(conn):
        try:
            cur = conn.execute(sql)
            columns = [d[0] for d in (cur.description or [])]
            rows = [tuple(r) for r in cur.fetchall()]
        except sqlite3.Error as exc:
            return ResultTable(error=str(exc))
        except Exception as exc:  # defensive: never let a bad query crash the run
            return ResultTable(error=f"{type(exc).__name__}: {exc}")

    if not _ORDER_BY_RE.search(sql):
        rows = sorted(rows, key=_canonical_sort_key)

    return ResultTable(columns=columns, rows=rows)


__all__ = ["run_query"]
