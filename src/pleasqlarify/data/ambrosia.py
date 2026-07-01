"""AMBROSIA data loading and schema extraction (spec 01).

The full AMBROSIA benchmark is loaded via the optional ``datasets`` extra (see
``load_ambrosia``). For offline development and tests, ``schema_from_sqlite``
reconstructs a :class:`DbSchema` from any SQLite file, and the pipeline can run
against locally-built fixture databases (see ``tests/conftest.py``).
"""

from __future__ import annotations

import ast
import csv
import hashlib
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from typing import Iterator, Optional

from ..model.types import AmbiguityType, DbSchema

# The real AMBROSIA download (spec 01, F1). It is NOT on HuggingFace; it is a
# password-protected direct download the authors ask not to be redistributed, so
# it is kept out of version control (see .gitignore) and read from this local
# extraction directory. Override with the PLEASQL_AMBROSIA_ROOT env var.
DEFAULT_AMBROSIA_ROOT = os.environ.get("PLEASQL_AMBROSIA_ROOT", "data/ambrosia")


@dataclass
class GoldQuery:
    intent_label: str
    sql: str


@dataclass
class AmbrosiaSample:
    sample_id: str
    ambiguity_type: AmbiguityType
    utterance: str
    db_path: str
    schema: DbSchema
    gold_queries: list[GoldQuery] = field(default_factory=list)


def schema_from_sqlite(db_path: str) -> DbSchema:
    """Reconstruct a :class:`DbSchema` from a SQLite database via PRAGMA."""
    schema = DbSchema()
    with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as conn:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        for t in tables:
            cols: list[str] = []
            for row in conn.execute(f'PRAGMA table_info("{t}")'):
                col_name, col_type = row[1], row[2]
                cols.append(col_name)
                schema.column_types[f"{t}.{col_name}"] = col_type
            schema.tables[t] = cols
    return schema


def load_ambrosia(
    root: str = DEFAULT_AMBROSIA_ROOT,
    split: str = "test",
    ambiguity_type: Optional[AmbiguityType] = None,
    domain: Optional[str] = None,
    limit: Optional[int] = None,
) -> Iterator[AmbrosiaSample]:
    """Yield ambiguous :class:`AmbrosiaSample` from a local AMBROSIA extraction.

    Resolves spec 01, F1: the benchmark ships as a CSV (``data/ambrosia.csv``)
    plus per-database SQLite files. Each ambiguous row carries the ambiguous
    utterance (``ambig_question``), the list of gold interpretation queries
    (``ambig_queries``, a Python-list literal), the ambiguity type, the domain,
    and a relative ``db_file`` path. We read only the fields we need with the
    stdlib csv module (no pandas dependency).
    """
    csv_path = os.path.join(root, "data", "ambrosia.csv")
    if not os.path.exists(csv_path):
        raise FileNotFoundError(
            f"AMBROSIA CSV not found at {csv_path}. Download the benchmark from "
            "https://ambrosia-benchmark.github.io/ and extract it to "
            f"{root!r} (or set PLEASQL_AMBROSIA_ROOT)."
        )
    csv.field_size_limit(10_000_000)  # db_dump fields are large
    count = 0
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if str(row.get("is_ambiguous")).lower() != "true":
                continue
            if split and row.get("split") != split:
                continue
            atype = row.get("ambig_type")
            if ambiguity_type and atype != ambiguity_type:
                continue
            if domain and row.get("domain") != domain:
                continue
            try:
                gold_sqls = ast.literal_eval(row["ambig_queries"])
            except (ValueError, SyntaxError):
                continue
            if not isinstance(gold_sqls, list) or len(gold_sqls) < 2:
                continue
            db_path = os.path.join(root, row["db_file"])
            if not os.path.exists(db_path):
                continue
            # One database hosts several distinct ambiguous questions, so the DB
            # filename is NOT a unique sample id — disambiguate with a short hash
            # of the utterance (else different questions collide and overwrite each
            # other's results).
            db_stem = os.path.splitext(os.path.basename(row["db_file"]))[0]
            q_hash = hashlib.blake2b(
                row["ambig_question"].encode(), digest_size=3
            ).hexdigest()
            yield AmbrosiaSample(
                sample_id=f"{db_stem}#{q_hash}",
                ambiguity_type=atype,  # type: ignore[arg-type]
                utterance=row["ambig_question"],
                db_path=db_path,
                schema=schema_from_sqlite(db_path),
                gold_queries=[
                    GoldQuery(intent_label=f"interp{i}", sql=q)
                    for i, q in enumerate(gold_sqls)
                ],
            )
            count += 1
            if limit and count >= limit:
                return


__all__ = ["GoldQuery", "AmbrosiaSample", "schema_from_sqlite", "load_ambrosia"]
