"""Evaluation conditions: baselines + 'ours' variants (spec 09).

Each condition is a decision-variable *selection policy* plus two Session build
axes (clustering on/off, grouped/atomic variables), plugged into the same repair
loop. The five named conditions match Figure 5's legend.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Optional

from ..model.types import Belief, DecisionVariable
from ..pipeline.ranking import best_variable, rank_variables
from ..session import Session

# A policy chooses the next variable to ask given belief + candidate variables.
Policy = Callable[[Belief, list[DecisionVariable]], Optional[DecisionVariable]]


def eig_policy(belief: Belief, variables: list[DecisionVariable]) -> Optional[DecisionVariable]:
    """argmax expected information gain (Eq. 8)."""
    return best_variable(belief, variables)


def max_prob_first_policy(
    belief: Belief, variables: list[DecisionVariable]
) -> Optional[DecisionVariable]:
    """Greedy: split on the value with the highest current posterior first (spec 09)."""
    rank_variables(belief, variables)  # populate .ig for informativeness filter
    informative = [v for v in variables if v.ig > 1e-12]
    if not informative:
        return None

    def top_value_mass(v: DecisionVariable) -> float:
        p_true = sum(p for cid, p in belief.items() if v.value_of(cid))
        return max(p_true, 1.0 - p_true)

    return max(informative, key=top_value_mass)


def make_random_policy(seed: int = 0) -> Policy:
    rng = random.Random(seed)

    def policy(belief: Belief, variables: list[DecisionVariable]) -> Optional[DecisionVariable]:
        rank_variables(belief, variables)
        informative = [v for v in variables if v.ig > 1e-12]
        if not informative:
            return None
        return rng.choice(sorted(informative, key=lambda v: v.id))

    return policy


@dataclass(frozen=True)
class Condition:
    name: str
    clustering: bool
    mode: str  # "atomic" | "grouped"
    policy: Policy

    def select(self, session: Session) -> Optional[DecisionVariable]:
        return self.policy(session.belief, session.variables)


def five_conditions(seed: int = 0) -> list[Condition]:
    """The five conditions compared in Figure 5 (spec 09)."""
    return [
        Condition("Baseline Random + Atomic", False, "atomic", make_random_policy(seed)),
        Condition("Baseline Max-Prob-First + Atomic", False, "atomic", max_prob_first_policy),
        # 'ERG' in the Fig 5 legend == EIG without clustering (spec 09/10, A16).
        Condition("Baseline ERG + Atomic", False, "atomic", eig_policy),
        Condition("Ours: Clustering + EIG + Atomic", True, "atomic", eig_policy),
        Condition("Ours: Clustering + EIG + Feature Grouping", True, "grouped", eig_policy),
    ]


__all__ = [
    "Policy",
    "eig_policy",
    "max_prob_first_policy",
    "make_random_policy",
    "Condition",
    "five_conditions",
]
