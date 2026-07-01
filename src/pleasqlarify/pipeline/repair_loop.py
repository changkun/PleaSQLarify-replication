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


def is_terminated(intents: IntentSet, ranked: list[DecisionVariable]) -> bool:
    """Terminate on a single functional class or no informative variable (A12)."""
    if len(intents) <= 1:
        return True
    return not any(v.ig > 1e-12 for v in ranked)


__all__ = ["consistent", "filter_action_space", "is_terminated"]
