"""AMBROSIA data loading and schema extraction (spec 01).

The full AMBROSIA benchmark is loaded via the optional ``datasets`` extra (see
``load_ambrosia``). For offline development and tests, ``schema_from_sqlite``
reconstructs a :class:`DbSchema` from any SQLite file, and the pipeline can run
against locally-built fixture databases (see ``tests/conftest.py``).
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass, field

from ..model.types import AmbiguityType, DbSchema


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


def load_ambrosia(dataset_id: str = "cambridgeltl/AMBROSIA", split: str = "test"):
    """Load real AMBROSIA samples (optional extra) — NOT YET WIRED.

    This is an explicit, unimplemented boundary, not a working loader. The paper
    cites AMBROSIA (ref [35]) but does not give a concrete HuggingFace id/split or
    field schema (spec 01, F1), so the mapping from dataset rows to
    :class:`AmbrosiaSample` (db file materialization, gold-query fields, ambiguity
    type) must be pinned against the actual dataset before the real quantitative
    evaluation (spec 10 / Figure 5) can run on non-toy data.

    Until then the pipeline and tests use fixture / demo databases. See the
    "empirical validation gap" note in the project README.
    """
    raise NotImplementedError(
        "Real AMBROSIA loading is not wired yet (spec 01, F1). Pin the HuggingFace "
        "dataset id/split and field mapping against the real dataset, then "
        "materialize each sample's SQLite DB and its gold queries into an "
        f"AmbrosiaSample. Requested: dataset_id={dataset_id!r}, split={split!r}."
    )


__all__ = ["GoldQuery", "AmbrosiaSample", "schema_from_sqlite", "load_ambrosia"]
