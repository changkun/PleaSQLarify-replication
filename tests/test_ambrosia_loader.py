"""AMBROSIA loader tests (skipped unless the benchmark is downloaded locally)."""

from __future__ import annotations

import os

import pytest

from pleasqlarify.data.ambrosia import DEFAULT_AMBROSIA_ROOT, load_ambrosia
from pleasqlarify.data.execution import run_query

_CSV = os.path.join(DEFAULT_AMBROSIA_ROOT, "data", "ambrosia.csv")
pytestmark = pytest.mark.skipif(
    not os.path.exists(_CSV), reason="AMBROSIA not downloaded (see README)"
)


def test_loads_filmmaking_samples():
    samples = list(load_ambrosia(domain="Filmmaking", limit=5))
    assert samples
    for s in samples:
        assert s.ambiguity_type in ("scope", "attachment", "vague")
        assert len(s.gold_queries) >= 2
        assert s.schema.tables
        assert os.path.exists(s.db_path)


def test_gold_queries_execute_and_differ():
    s = next(load_ambrosia(domain="Filmmaking"))
    outputs = [run_query(s.db_path, g.sql) for g in s.gold_queries]
    assert all(o.error is None for o in outputs)
    # distinct interpretations should not all produce identical output
    signatures = {(tuple(o.columns), tuple(o.rows)) for o in outputs}
    assert len(signatures) >= 2
