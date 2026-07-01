"""Step 1 - candidate generation: sample the action space A (spec 03)."""

from __future__ import annotations

import re

from ..llm.client import LLMClient
from ..model.types import ActionSpace, Candidate, DbSchema
from .features import is_parseable

_SQL_FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def build_prompt(utterance: str, schema: DbSchema) -> str:
    """Zero-shot generation prompt with full DDL context (spec 03, A1)."""
    ddl_lines = []
    for table, cols in schema.tables.items():
        col_defs = ", ".join(
            f"{c} {schema.column_types.get(f'{table}.{c}', 'TEXT')}" for c in cols
        )
        ddl_lines.append(f"CREATE TABLE {table} ({col_defs});")
    ddl = "\n".join(ddl_lines)
    return (
        "You are a text-to-SQL system. Given the database schema and a question, "
        "return exactly one SQL query answering the question against this schema. "
        "Return only the SQL, no explanation.\n\n"
        f"Schema:\n{ddl}\n\nQuestion: {utterance}\nSQL:"
    )


def _clean(raw: str) -> str:
    m = _SQL_FENCE.search(raw)
    text = m.group(1) if m else raw
    return text.strip().rstrip(";").strip()


def generate_candidates(
    utterance: str,
    schema: DbSchema,
    client: LLMClient,
    n: int = 50,
    temperature: float = 0.7,
) -> ActionSpace:
    """Sample N queries, drop unparseable, collapse byte-identical (spec 03, A2).

    Returns candidates with stable ids ``c0..`` and ``gen_count`` set to the
    number of identical raw generations (the raw material for the prior, spec 07).
    """
    raw = client.generate(build_prompt(utterance, schema), n=n, temperature=temperature)
    counts: dict[str, int] = {}
    order: list[str] = []
    for r in raw:
        sql = _clean(r)
        if not sql or not is_parseable(sql):
            continue  # drop syntactically invalid (spec 03 footnote 4)
        if sql not in counts:
            counts[sql] = 0
            order.append(sql)
        counts[sql] += 1

    return [
        Candidate(id=f"c{i}", sql=sql, gen_count=counts[sql])
        for i, sql in enumerate(order)
    ]


__all__ = ["build_prompt", "generate_candidates"]
