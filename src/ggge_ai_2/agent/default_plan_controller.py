from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, Protocol

from ggge_ai_2.agent.belief import Belief
from ggge_ai_2.agent.contract import Plan, Step
from ggge_ai_2.agent.ui_steps import first_move, operation_step
from ggge_ai_2.uisim.contract import UiScreen, UiSim, UiState


class Reflex(Protocol):
    def still_valid(self, belief: Belief) -> bool: ...

    def react(self, belief: Belief) -> Step | None: ...


@dataclass(frozen=True)
class PlanReflex:
    plan: Plan

    def still_valid(self, belief: Belief) -> bool:
        return self.plan.still_valid(belief)

    def react(self, belief: Belief) -> Step | None:
        return self.plan.next(belief) if self.plan.still_valid(belief) else None


@dataclass(frozen=True)
class DefaultPlanController:
    BATTLE_MAP: ClassVar[UiState] = UiState(UiScreen.PLAYER_PHASE_OVERVIEW)

    reflexes: tuple[Reflex, ...]
    uisim: UiSim
    screen: tuple[int, int]

    def goal_reached(self, belief: Belief) -> bool:
        # TODO(#105): the stage goal.
        return False

    def think(self, belief: Belief, history: Sequence[object]) -> ReflexPlan | None:
        # TODO(#105): before the map, check AUTO and '顯示方格'. On the map, give an
        #     unrecorded map to the map sync plan and a recorded map to the battle
        #     plan. After the map is explored, leave the stage.
        if belief.ui == self.BATTLE_MAP:
            return None
        to_map = UiShiftPlan(self.BATTLE_MAP, self.uisim, self.screen)
        return ReflexPlan(self.reflexes, to_map)

    def review(self, plan: ReflexPlan, belief: Belief) -> object:
        # TODO: the shape of a review is deferred.
        return plan


@dataclass(frozen=True)
class UiShiftPlan:
    goal: UiState
    uisim: UiSim
    screen: tuple[int, int]

    def still_valid(self, belief: Belief) -> bool:
        return belief.ui != self.goal and first_move(self.uisim, belief.ui, self.goal) is not None

    def next(self, belief: Belief) -> Step:
        move = first_move(self.uisim, belief.ui, self.goal)
        assert move is not None, "the main loop takes a step only from a valid plan"
        operation, _ = move
        return operation_step(operation, belief, self.uisim, self.screen)


@dataclass(frozen=True)
class ReflexPlan:
    reflexes: tuple[Reflex, ...]
    inner: Plan

    def still_valid(self, belief: Belief) -> bool:
        return any(r.still_valid(belief) for r in self.reflexes) or self.inner.still_valid(belief)

    def next(self, belief: Belief) -> Step:
        return self._react(belief) or self.inner.next(belief)

    def _react(self, belief: Belief) -> Step | None:
        for reflex in self.reflexes:
            step = reflex.react(belief)
            if step is not None:
                return step
        return None
