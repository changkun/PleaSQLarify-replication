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
    """Yield :class:`AmbrosiaSample` from the HuggingFace dataset (optional extra).

    Requires ``pip install .[data]``. The concrete dataset id / split is an
    undocumented decision (spec 01, F1) resolved here to a default; override via
    the arguments. This is intentionally thin — the mapping from AMBROSIA fields
    to :class:`AmbrosiaSample` is finalized once the exact schema is pinned.
    """
    try:
        from datasets import load_dataset  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "AMBROSIA loading needs the 'data' extra: pip install .[data]"
        ) from exc

    ds = load_dataset(dataset_id, split=split)  # pragma: no cover - network
    for i, row in enumerate(ds):  # pragma: no cover - network
        # Field names are pinned when F1 is resolved against the real dataset.
        yield row, i


__all__ = ["GoldQuery", "AmbrosiaSample", "schema_from_sqlite", "load_ambrosia"]
