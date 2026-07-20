"""Step 5 - stateless helpers for the iterative repair loop (spec 08).

The stateful driver is :class:`pleasqlarify.session.Session`; these are the pure
pieces it composes so they can be unit-tested in isolation.
"""

from __future__ import annotations

from ..model.types import ActionSpace, Belief, Candidate, DecisionVariable, IntentSet


def consistent(candidate: Candidate, variable: DecisionVariable, value: bool) -> bool:
    """Whether a candidate agrees with answering ``variable`` = ``value``.

    Yes (True) keeps candidates that contain the group; No (False) keeps those
    that exclude it (spec 08: "retain only actions consistent with the stated
    preference").
    """
    return (variable.group <= candidate.z) == value


def filter_action_space(
    candidates: ActionSpace, variable: DecisionVariable, value: bool
) -> ActionSpace:
    return [c for c in candidates if consistent(c, variable, value)]


TERMINATION_RULES = ("cluster_or_uninformative", "uninformative_only", "similarity_one")

# The authors stop when the surviving pool is functionally identical, i.e. mean
# pairwise similarity >= 1 - tol (their stop_mode="sim1", sim_stop_tol=1e-9).
SIM_STOP_TOL = 1e-9


def is_terminated(
    intents: IntentSet,
    ranked: list[DecisionVariable],
    rule: str = "cluster_or_uninformative",
    mean_similarity: float | None = None,
) -> bool:
    """Whether the repair loop should stop (assumption **A12**).

    * ``cluster_or_uninformative`` (default, the paper's reading) - stop once the
      survivors form a single functional class, or nothing informative is left.
    * ``uninformative_only`` - ignore the cluster count and keep asking while any
      variable still has positive information gain. This matters when clustering
      **over-merges**: a single cluster can still span several gold intents, and
      the default rule stops there while questions remain that would separate them.
    * ``similarity_one`` - the authors' rule: stop once the survivors are
      functionally identical (mean pairwise similarity >= 1), or nothing
      informative remains. Stricter than the cluster-count rule: a single cluster
      whose members still differ functionally keeps going.
    """
    if rule == "similarity_one":
        if mean_similarity is not None and mean_similarity >= 1.0 - SIM_STOP_TOL:
            return True
        return not any(v.ig > 1e-12 for v in ranked)
    if rule == "uninformative_only":
        return not any(v.ig > 1e-12 for v in ranked)
    if rule != "cluster_or_uninformative":
        raise ValueError(f"unknown termination rule: {rule!r}")
    if len(intents) <= 1:
        return True
    return not any(v.ig > 1e-12 for v in ranked)


__all__ = ["consistent", "filter_action_space", "is_terminated", "TERMINATION_RULES"]
