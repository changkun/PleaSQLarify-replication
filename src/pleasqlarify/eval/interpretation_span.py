"""Does a candidate pool actually contain the ambiguity we ask the system to resolve?

The whole §7 evaluation presupposes that the generated pool spans more than one
gold interpretation. Measuring that presupposition turns out to be delicate, and
two natural measures are both wrong on AMBROSIA:

* **Exact row-multiset match** is too strict: a candidate that realises a gold
  interpretation but projects an extra column (``FirstName, LastName`` vs
  ``LastName``) shares no whole row with it and is spuriously rejected.
* **"Contains gold i's distinctive values"** is broken by *nested* golds. AMBROSIA
  ambiguities are usually UNIONs that differ in which side carries a filter, so one
  gold's output is frequently a **subset** of the other's (102/150 samples in the
  150-sample run). The subset gold then has an empty distinctive set and becomes
  uncoverable *by construction*, forcing the measured span to 0 regardless of what
  the model produced.

:func:`realised_interpretations` handles both: a candidate realises gold *i* when
it contains **all** of gold *i*'s output values and **none** of the values that are
extra to any competing gold. Extra projected columns are tolerated (they add values
no gold claims); nesting is handled, because the larger gold's extra values are
exactly what excludes the smaller one.

Values are compared as a flattened set, so this is a *lower bound* on span: it
demands strict execution-level agreement and never credits a near miss.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from ..data.execution import run_query
from ..model.types import ResultTable


def output_values(rt: Optional[ResultTable]) -> set[str]:
    """Flattened set of cell values; degenerate outputs contribute nothing."""
    if rt is None or rt.is_error or rt.is_empty:
        return set()
    return {"" if v is None else str(v) for row in rt.rows for v in row}


def realised_interpretations(
    candidate_values: Sequence[set[str]], gold_values: Sequence[set[str]]
) -> set[int]:
    """Indices of gold interpretations some candidate realises at execution level."""
    covered: set[int] = set()
    for i, gv in enumerate(gold_values):
        if not gv:
            continue
        extra_elsewhere: set[str] = set()
        for j, other in enumerate(gold_values):
            if j != i:
                extra_elsewhere |= other - gv
        for cv in candidate_values:
            if cv and gv <= cv and not (extra_elsewhere & cv):
                covered.add(i)
                break
    return covered


@dataclass
class SpanReport:
    usable: int = 0          # samples whose golds differ in output at all
    identical_golds: int = 0  # dropped: gold interpretations are output-identical
    span_two_plus: int = 0
    span_one: int = 0
    span_none: int = 0

    @property
    def span_rate(self) -> float:
        return self.span_two_plus / self.usable if self.usable else 0.0

    def add(self, covered: set[int]) -> None:
        self.usable += 1
        if len(covered) >= 2:
            self.span_two_plus += 1
        elif len(covered) == 1:
            self.span_one += 1
        else:
            self.span_none += 1


def sample_span(candidates, gold_sqls: list[str], db_path: str) -> Optional[set[int]]:
    """Which gold interpretations this sample's candidate pool realises.

    Returns ``None`` when the gold interpretations are indistinguishable by output,
    so the sample cannot inform the span question either way.
    """
    gold_values = [output_values(run_query(db_path, g)) for g in gold_sqls]
    if len(gold_values) < 2 or len({frozenset(g) for g in gold_values}) < 2:
        return None
    return realised_interpretations([output_values(c.result) for c in candidates], gold_values)


__all__ = [
    "output_values",
    "realised_interpretations",
    "sample_span",
    "SpanReport",
]
