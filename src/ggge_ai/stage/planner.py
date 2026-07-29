"""GOAP A*：符號狀態前向搜尋，邊權全部向注入的 Advisor 要。"""

from __future__ import annotations

import heapq
from collections.abc import Iterator
from dataclasses import dataclass

from ..sandbox.advise import Advisor, Pricing
from .actions import Action, candidates
from .goals import Goal
from .state import Phase, StageState, next_player_phase


@dataclass(frozen=True)
class PlannerConfig:
    max_expansions: int = 5_000
    phase_cost: float = 1.0
    min_action_cost: float = 0.0


@dataclass(frozen=True)
class Step:
    action: Action
    pricing: Pricing


@dataclass(frozen=True)
class Plan:
    steps: tuple[Step, ...]
    cost: float
    expanded: int
    truncated: bool = False


@dataclass(frozen=True)
class NoPlan:
    """規劃失敗是值不是例外——誠實停止的觸發點，跟 HTN 那邊同一個紀律。"""

    reason: str
    expanded: int


def plan(
    state: StageState,
    goal: Goal,
    advisor: Advisor[StageState, Action],
    config: PlannerConfig = PlannerConfig(),
) -> Plan | NoPlan:
    """找到完整解才回計畫，但只交付回合交界之前的前綴。

    跨過敵方回合的保證早就不是保證了，交界因此是天然的重規劃邊界；
    搜尋仍要看完整條路，否則分不出「這回合做不完」與「根本做不到」。
    """
    if goal.is_satisfied(state):
        return Plan((), 0.0, 0)

    counter = 0
    heap: list[tuple[float, int, StageState]] = [(_heuristic(goal, state, config), counter, state)]
    cost_to: dict[StageState, float] = {state: 0.0}
    came_from: dict[StageState, tuple[StageState, Step | None]] = {}
    closed: set[StageState] = set()
    expanded = 0

    while heap:
        _, _, current = heapq.heappop(heap)
        if current in closed:
            continue
        if goal.is_satisfied(current):
            return _assemble(came_from, current, cost_to[current], expanded)
        closed.add(current)

        expanded += 1
        if expanded > config.max_expansions:
            return NoPlan("expansion limit reached", expanded)

        for successor, step, edge_cost in _successors(current, advisor, config):
            if successor in closed:
                continue
            tentative = cost_to[current] + edge_cost
            if tentative < cost_to.get(successor, float("inf")):
                cost_to[successor] = tentative
                came_from[successor] = (current, step)
                counter += 1
                heapq.heappush(
                    heap, (tentative + _heuristic(goal, successor, config), counter, successor)
                )

    return NoPlan("search space exhausted", expanded)


def _heuristic(goal: Goal, state: StageState, config: PlannerConfig) -> float:
    return config.min_action_cost * goal.unmet(state)


def _successors(
    state: StageState, advisor: Advisor[StageState, Action], config: PlannerConfig
) -> Iterator[tuple[StageState, Step | None, float]]:
    options = candidates(state)
    if options:
        prices = tuple(advisor.price(state, options))
        if len(prices) != len(options):
            raise ValueError(
                f"Advisor 計價 {len(prices)} 筆對不上候選 {len(options)} 筆：契約要求逐位對齊"
            )
        for action, pricing in zip(options, prices, strict=True):
            if pricing is None:
                continue
            if pricing.cost < 0:
                raise ValueError(f"Advisor 對 {action.label} 給了負計價 {pricing.cost}")
            yield action.apply(state, pricing), Step(action, pricing), pricing.cost

    if state.phase is Phase.PLAYER and not state.actionable:
        yield next_player_phase(state), None, config.phase_cost


def _assemble(
    came_from: dict[StageState, tuple[StageState, Step | None]],
    final: StageState,
    cost: float,
    expanded: int,
) -> Plan:
    edges: list[Step | None] = []
    cursor = final
    while cursor in came_from:
        cursor, step = came_from[cursor]
        edges.append(step)
    edges.reverse()

    steps: list[Step] = []
    truncated = False
    for edge in edges:
        if edge is None:
            truncated = True
            break
        steps.append(edge)
    return Plan(tuple(steps), cost, expanded, truncated)
