"""Step 4 - expected information gain ranking of decision variables (spec 07).

Implements Eq. 7 (expected information gain) and Eq. 8 (argmax selection).
"""

from __future__ import annotations

from ..model.types import Belief, DecisionVariable
from .belief import condition, entropy


def information_gain(belief: Belief, variable: DecisionVariable) -> float:
    """IG_t(Z) = H(p_t) - Σ_v P_t(Z=v) H(p_t(·|Z=v))  (Eq. 7)."""
    h_prior = entropy(belief)
    expected_conditional = 0.0
    for value in (True, False):
        p_v = sum(p for cid, p in belief.items() if variable.value_of(cid) == value)
        if p_v <= 0.0:
            continue
        expected_conditional += p_v * entropy(condition(belief, variable, value))
    return h_prior - expected_conditional


def _balance(belief: Belief, variable: DecisionVariable) -> float:
    """How balanced the split is (0 = perfectly balanced) - deterministic tiebreak."""
    p_true = sum(p for cid, p in belief.items() if variable.value_of(cid))
    return abs(p_true - 0.5)


def rank_variables(
    belief: Belief, variables: list[DecisionVariable]
) -> list[DecisionVariable]:
    """Return variables ordered by IG desc; ties -> more balanced split, then label.

    Also writes ``variable.ig`` in place so views can display it (spec 13).
    """
    for v in variables:
        v.ig = information_gain(belief, v)
    return sorted(
        variables,
        key=lambda v: (-v.ig, _balance(belief, v), v.label),
    )


def best_variable(
    belief: Belief, variables: list[DecisionVariable]
) -> DecisionVariable | None:
    """Z*_t = argmax_Z IG_t(Z)  (Eq. 8), or None if nothing is informative."""
    ranked = rank_variables(belief, variables)
    ranked = [v for v in ranked if v.ig > 1e-12]
    return ranked[0] if ranked else None


__all__ = ["information_gain", "rank_variables", "best_variable"]
