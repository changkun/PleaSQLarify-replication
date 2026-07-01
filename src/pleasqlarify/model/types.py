"""Shared data model and notation for the whole pipeline.

Implements the keystone spec ``specs/foundations/02-data-model-and-notation.md``.
No behavior lives here beyond trivial helpers; every downstream module produces
or consumes these structures so the Section 5 pipeline composes.

Notation map (paper -> code):
    A            -> ActionSpace (list[Candidate])
    z(a)         -> Candidate.z (frozenset of active atomic-feature indices)
    m(a, C)      -> Candidate.result (ResultTable)
    M_t          -> IntentSet (list[Cluster]); one cluster == one intent
    Z_t          -> DecisionVariable
    p_t(m)       -> Belief (dict[cluster_id, float])
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

AmbiguityType = Literal["scope", "attachment", "vague"]

# ---------------------------------------------------------------------------
# Database side (spec 01)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Column:
    table: str
    name: str
    type: str = ""

    @property
    def qualified(self) -> str:
        return f"{self.table}.{self.name}"


@dataclass
class DbSchema:
    """Table -> ordered column names, plus flat column lookup."""

    tables: dict[str, list[str]] = field(default_factory=dict)
    column_types: dict[str, str] = field(default_factory=dict)  # "table.col" -> type

    def columns(self) -> list[Column]:
        out: list[Column] = []
        for t, cols in self.tables.items():
            for c in cols:
                out.append(Column(t, c, self.column_types.get(f"{t}.{c}", "")))
        return out

    def find_table_for_column(self, col: str) -> Optional[str]:
        """Return the (unique) table owning an unqualified column, else None."""
        owners = [t for t, cols in self.tables.items() if col in cols]
        return owners[0] if len(owners) == 1 else None


@dataclass
class ResultTable:
    """m(a, C): the outcome of executing an action against a database."""

    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def n_rows(self) -> int:
        return len(self.rows)

    @property
    def n_cols(self) -> int:
        return len(self.columns)

    @property
    def is_error(self) -> bool:
        return self.error is not None

    @property
    def is_empty(self) -> bool:
        return not self.is_error and self.n_rows == 0


# ---------------------------------------------------------------------------
# Atomic features (spec 05)
# ---------------------------------------------------------------------------

AtomKind = Literal[
    "SELECT_COL",
    "SELECT_STAR",
    "AGG",
    "DISTINCT",
    "FROM_TABLE",
    "JOIN",
    "WHERE_PRED",
    "GROUP_BY",
    "HAVING",
    "ORDER_BY",
    "LIMIT",
]


@dataclass(frozen=True)
class AtomicFeature:
    """One dimension of z: the presence of a single atomic action component."""

    index: int
    kind: AtomKind
    payload: str  # canonical human-readable rendering, e.g. "SELECT Reviews.Opinion"

    @property
    def keyword(self) -> str:
        """Keyword span shown with a black background in the UI (spec 14)."""
        return self.payload.split(" ", 1)[0]

    @property
    def value(self) -> str:
        """Value span shown with a light-gray background in the UI (spec 14)."""
        parts = self.payload.split(" ", 1)
        return parts[1] if len(parts) > 1 else ""


@dataclass
class FeatureVocabulary:
    """Index-ordered union of atoms across A, frozen for the session (spec 02, M1)."""

    features: list[AtomicFeature] = field(default_factory=list)
    _by_payload: dict[str, int] = field(default_factory=dict, repr=False)

    @property
    def d(self) -> int:
        return len(self.features)

    def intern(self, kind: AtomKind, payload: str) -> int:
        """Return the index for an atom, adding it to the vocabulary if new."""
        if payload in self._by_payload:
            return self._by_payload[payload]
        idx = len(self.features)
        self.features.append(AtomicFeature(idx, kind, payload))
        self._by_payload[payload] = idx
        return idx

    def label_for(self, group: "frozenset[int] | list[int]") -> str:
        return " + ".join(self.features[i].payload for i in sorted(group))


# ---------------------------------------------------------------------------
# Actions and the action space A (specs 03/04/05)
# ---------------------------------------------------------------------------


@dataclass
class Candidate:
    """A candidate action a in A (here, a SQL query)."""

    id: str
    sql: str
    z: frozenset[int] = frozenset()  # active atomic-feature indices (spec 05)
    result: Optional[ResultTable] = None  # m(a, C) (spec 04)
    cluster_id: Optional[int] = None  # functional cluster (spec 04)
    gen_count: int = 1  # #times sampled; informs the prior (spec 03/07)


ActionSpace = list[Candidate]


# ---------------------------------------------------------------------------
# Intents / clusters M (spec 04) and decision variables Z (spec 06/07)
# ---------------------------------------------------------------------------


@dataclass
class Cluster:
    """A functional cluster == an intent m in M (spec 02, M2)."""

    id: int
    member_ids: list[str]
    representative_id: str


IntentSet = list[Cluster]


@dataclass
class DecisionVariable:
    """Z_t: a (grouped) atomic-feature decision to clarify (spec 06/07)."""

    id: str
    group: frozenset[int]  # indices of the grouped atomic features g
    label: str
    ig: float = 0.0  # expected information gain (spec 07)
    in_prob: float = 1.0  # implicit-inclusion probability p(z_Z=1|z_g=1) (spec 06)
    # which cluster ids carry this group (Z_t(m) == True):
    contains_cluster_ids: frozenset[int] = frozenset()

    def value_of(self, cluster_id: int) -> bool:
        """Z_t(m): does intent m carry this group?"""
        return cluster_id in self.contains_cluster_ids


Belief = dict[int, float]  # p_t(m): cluster_id -> probability, sums to 1


__all__ = [
    "AmbiguityType",
    "Column",
    "DbSchema",
    "ResultTable",
    "AtomKind",
    "AtomicFeature",
    "FeatureVocabulary",
    "Candidate",
    "ActionSpace",
    "Cluster",
    "IntentSet",
    "DecisionVariable",
    "Belief",
]
