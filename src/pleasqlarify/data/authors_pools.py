"""Load the authors' precomputed generation pools (spec 17 §3).

Their supplement ships ``27154505_diverse_sql_output.jsonl``: 300 ambiguous
questions (100 per ambiguity type) with the candidate pool that produced the
paper's numbers (median ~95 candidates each). Using it removes candidate
generation — the one thing the supplement does *not* specify — as a confound, and
costs no API calls.

Each record carries a complete ``db_dump`` (schema **and** INSERTs), so the
database is materialised from the pool file itself; no AMBROSIA extraction is
needed for this path.

The file is AMBROSIA-derived and is **not** redistributed here: point
``--pools`` at your own copy of the authors' supplement.
"""

from __future__ import annotations

import hashlib
import json
import re
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

import sqlglot

from ..model.types import DbSchema
from .ambrosia import schema_from_sqlite


@dataclass
class AuthorsSample:
    sample_id: str
    ambiguity_type: str
    utterance: str
    db_path: str
    schema: DbSchema
    gold_queries: list          # objects exposing .sql, like AmbrosiaSample
    generated_sql: list[str]
    domain: Optional[str] = None
    split: Optional[str] = None


@dataclass(frozen=True)
class _Gold:
    sql: str
    intent_label: str = ""


_TRAILING_COMMA = re.compile(r",(\s*)\)\s*$")


def repair_dump(db_dump: str) -> str:
    """Fix malformed DDL in the authors' dumps (10 of their 300 records).

    Their `CREATE TABLE` statements sometimes carry a trailing comma before the
    closing paren (``job_id INTEGER,\\n)``), which SQLite rejects. The repair is
    scoped to statements that *begin* with CREATE TABLE, so INSERT payloads — and
    therefore any string literal that happens to contain ``,)`` — are never
    rewritten.
    """
    out = []
    for stmt in db_dump.split(";\n"):
        if stmt.lstrip().upper().startswith("CREATE TABLE"):
            stmt = _TRAILING_COMMA.sub(r"\1)", stmt.rstrip())
        out.append(stmt)
    return ";\n".join(out)


def materialize_db(db_dump: str, cache_dir: str, key: str) -> str:
    """Write ``db_dump`` to a SQLite file under ``cache_dir`` (idempotent)."""
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    # keep the filename URI-safe: '#'/'?' break sqlite's file: URIs
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in key)
    path = os.path.join(cache_dir, f"{safe}.sqlite")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    tmp = path + ".tmp"
    if os.path.exists(tmp):
        os.unlink(tmp)
    # The first attempt can fail part-way through, leaving tables behind, so the
    # repaired retry needs a *fresh* database rather than the half-built one.
    last: Exception | None = None
    for script in (db_dump, repair_dump(db_dump)):
        if os.path.exists(tmp):
            os.unlink(tmp)
        con = sqlite3.connect(tmp)
        try:
            con.executescript(script)
            con.commit()
            last = None
        except sqlite3.Error as exc:
            last = exc
        finally:
            con.close()
        if last is None:
            os.replace(tmp, path)
            return path
    if os.path.exists(tmp):
        os.unlink(tmp)
    raise last  # type: ignore[misc]


def _canonical(sql: str) -> Optional[str]:
    """Parser-normalized form of a query, for the authors' sample filter.

    Their filter compares the *parsed* representations produced by Spider's
    ``process_sql``; we normalize with sqlglot instead (our documented parser
    deviation, spec 05). Both answer the same question — "is this gold query
    present in the pool?" — but the equivalences differ slightly at the margin,
    so the resulting subsample need not be identical to theirs.
    """
    try:
        parsed = sqlglot.parse_one(sql, dialect="sqlite")
    except Exception:
        return None
    if parsed is None:
        return None
    return parsed.sql(dialect="sqlite", normalize=True, pretty=False).casefold()


def pool_contains_all_golds(generated_sql: list[str], gold_sqls: list[str]) -> bool:
    """The authors' sample filter (``run_eval.py:1522``).

    Keep a sample only when **every** gold query already appears among the
    generated queries. The paper's reported numbers are conditioned on this, so
    any comparison to Figure 5 must apply it or it measures a different
    population.
    """
    if not gold_sqls:
        return False
    pool = {c for c in (_canonical(s) for s in generated_sql) if c}
    golds = [_canonical(g) for g in gold_sqls]
    if any(g is None for g in golds):
        return False
    return all(g in pool for g in golds)


def load_authors_pools(
    pools_path: str,
    cache_dir: str = "data/authors_dbs",
    split: Optional[str] = "test",
    require_all_golds: bool = False,
    ambrosia_root: Optional[str] = None,
    stats: Optional[dict] = None,
) -> Iterator[AuthorsSample]:
    """Yield the authors' samples, materializing each database on the way.

    ``require_all_golds`` applies their sample filter; leave it off to measure how
    often the precondition holds.

    A few of their ``db_dump`` payloads are internally inconsistent (an INSERT
    naming a column the CREATE TABLE lacks). Those are not generically repairable,
    so we fall back to the real AMBROSIA database at ``db_file`` under
    ``ambrosia_root`` when available, and otherwise skip the sample. Counts land in
    ``stats`` so nothing is dropped silently.
    """
    if stats is None:
        stats = {}
    stats.setdefault("from_dump", 0)
    stats.setdefault("from_ambrosia", 0)
    stats.setdefault("skipped_unusable_db", 0)
    stats.setdefault("filtered_out", 0)
    with open(pools_path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if split is not None and rec.get("split") != split:
                continue
            gold_sqls = rec.get("ambig_queries") or rec.get("gold_queries") or []
            generated = rec.get("generated_sql") or []
            if not gold_sqls or not generated:
                continue
            if require_all_golds and not pool_contains_all_golds(generated, gold_sqls):
                stats["filtered_out"] += 1
                continue

            question = rec.get("ambig_question") or rec.get("original_question") or ""
            stem = Path(rec.get("db_file") or "db").stem
            qhash = hashlib.blake2b(question.encode(), digest_size=3).hexdigest()
            sample_id = f"{stem}#{qhash}"

            db_path = None
            dump = rec.get("db_dump")
            if dump:
                try:
                    db_path = materialize_db(dump, cache_dir, sample_id)
                    stats["from_dump"] += 1
                except sqlite3.Error:
                    db_path = None
            if db_path is None and ambrosia_root and rec.get("db_file"):
                candidate = os.path.join(ambrosia_root, rec["db_file"])
                if os.path.exists(candidate):
                    db_path = candidate
                    stats["from_ambrosia"] += 1
            if db_path is None:
                stats["skipped_unusable_db"] += 1
                continue
            try:
                schema = schema_from_sqlite(db_path)
            except Exception:
                stats["skipped_unusable_db"] += 1
                continue

            yield AuthorsSample(
                sample_id=sample_id,
                ambiguity_type=rec.get("ambig_type") or "unknown",
                utterance=question,
                db_path=db_path,
                schema=schema,
                gold_queries=[_Gold(sql=s) for s in gold_sqls],
                generated_sql=list(generated),
                domain=rec.get("domain"),
                split=rec.get("split"),
            )


__all__ = [
    "AuthorsSample",
    "load_authors_pools",
    "materialize_db",
    "pool_contains_all_golds",
]
