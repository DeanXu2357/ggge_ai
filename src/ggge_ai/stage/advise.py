"""The pricing contract between the planner and the advisor.

The engagement answers a distribution, so the price can fold the risk into the
cost. The guarantee holds only when it holds for every roll of the dice, so a
kill is the only guarantee. The planner walks the state from the guarantee and
harvests the rest by planning again.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class Guarantee(Enum):
    NONE = "none"
    KILL = "kill"


class Verdict(Enum):
    PURSUE = "pursue"
    WITHDRAW = "withdraw"


@dataclass(frozen=True)
class Pricing:
    """The cost is a non-negative edge weight of the plan. A negative weight
    breaks the closed set of the A-star search, and the planner refuses it.
    """

    cost: float
    guarantee: Guarantee = Guarantee.NONE
    note: str = ""


@dataclass(frozen=True)
class Appraisal:
    verdict: Verdict
    reason: str = ""


class Advisor[StateT, ActionT](Protocol):
    """A symbolic state and its candidate actions in, an appraisal and a price
    out.

    The 'price' method answers a sequence as long as the candidates, aligned
    one for one. None is no endorsement: the planner drops that candidate from
    the search, and never prices it itself.
    """

    def appraise(self, state: StateT) -> Appraisal: ...

    def price(self, state: StateT, candidates: Sequence[ActionT]) -> Sequence[Pricing | None]: ...
