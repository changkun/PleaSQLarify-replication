"""The authors' configuration as a single preset (spec 17).

Aligning to the supplementary code touched six independent knobs. Setting them
one at a time is how a "replication" silently ends up being a mixture, so this
module makes the authors' configuration a single named object, with our original
gap-fill configuration alongside it for comparison.

Nothing here invents a decision: every field cites the corresponding row of the
spec-17 table. Fields the supplement does **not** settle (candidate generation)
are deliberately absent — they are inputs, not configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class PipelineConfig:
    """Every decision the supplement settles, in one place."""

    name: str

    # A3/A4 — how outputs are compared
    similarity_style: str = "row_aligned"
    # A5 — how many functional clusters
    k_mode: str = "authors"
    linkage: str = "average"
    threshold: float = 0.1          # only consulted when k_mode == "threshold"
    # A6 — atom granularity
    where_granularity: str = "clause"
    # A8 — how multi-atom feature groups are formed
    group_mode: str = "mined"
    # A10 — what a decision variable partitions: "cluster" or "candidate"
    variable_space: str = "candidate"
    # A12 — when the repair loop stops
    termination: str = "similarity_one"
    # A14 — how candidates are labelled with a gold interpretation
    gold_assignment: str = "execution"   # "execution" | "embedding"
    # A15 — entropy units are fixed in eval.metrics (bits); recorded for provenance
    entropy_units: str = "bits"

    def session_kwargs(self) -> dict:
        """Keyword arguments for :func:`pleasqlarify.session.build_session`."""
        return {
            "k_mode": self.k_mode,
            "linkage": self.linkage,
            "threshold": self.threshold,
            "termination": self.termination,
            "serialization": self.similarity_style,
        }

    def as_dict(self) -> dict:
        return asdict(self)


#: The authors' actual configuration, as read from their supplementary code.
AUTHORS = PipelineConfig(name="authors")

#: What we had implemented before the supplement was available. Retained so the
#: two can be run head to head rather than argued about.
OURS_ORIGINAL = PipelineConfig(
    name="ours_original",
    similarity_style="header_rows",
    k_mode="threshold",
    linkage="average",
    threshold=0.1,
    where_granularity="predicate",
    group_mode="grouped",
    variable_space="cluster",
    termination="cluster_or_uninformative",
    gold_assignment="embedding",
    entropy_units="bits",   # our nats-era numbers are superseded either way
)

PRESETS = {p.name: p for p in (AUTHORS, OURS_ORIGINAL)}


def get_preset(name: str) -> PipelineConfig:
    try:
        return PRESETS[name]
    except KeyError:
        raise ValueError(
            f"unknown preset {name!r}; choose from {sorted(PRESETS)}"
        ) from None


__all__ = ["PipelineConfig", "AUTHORS", "OURS_ORIGINAL", "PRESETS", "get_preset"]
