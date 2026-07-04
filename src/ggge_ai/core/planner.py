from __future__ import annotations

import heapq
from collections.abc import Sequence
from dataclasses import dataclass

from .action import Action, Goal
from .state import WorldState


@dataclass
class PlanResult:
    actions: list[Action]
    total_cost: float
    expanded: int


class PlanNotFound(Exception):
    def __init__(self, expanded: int, exhausted: bool) -> None:
        self.expanded = expanded
        self.exhausted = exhausted
        detail = "search space exhausted" if exhausted else "expansion limit reached"
        super().__init__(f"no plan found ({detail}, expanded={expanded})")


def plan(
    initial: WorldState,
    goal: Goal,
    actions: Sequence[Action],
    max_expansions: int = 20_000,
) -> PlanResult:
    """A* forward search from initial state to any state satisfying the goal."""
    counter = 0
    open_heap: list[tuple[float, int, WorldState]] = [(goal.heuristic(initial), counter, initial)]
    g_cost: dict[WorldState, float] = {initial: 0.0}
    came_from: dict[WorldState, tuple[WorldState, Action]] = {}
    closed: set[WorldState] = set()
    expanded = 0

    while open_heap:
        _, _, current = heapq.heappop(open_heap)
        if current in closed:
            continue
        if goal.is_satisfied(current):
            return PlanResult(_reconstruct(came_from, current), g_cost[current], expanded)
        closed.add(current)

        expanded += 1
        if expanded > max_expansions:
            raise PlanNotFound(expanded, exhausted=False)

        for action in actions:
            if not action.check(current):
                continue
            neighbor = action.apply(current)
            if neighbor in closed:
                continue
            tentative = g_cost[current] + action.cost
            if tentative < g_cost.get(neighbor, float("inf")):
                g_cost[neighbor] = tentative
                came_from[neighbor] = (current, action)
                counter += 1
                heapq.heappush(
                    open_heap, (tentative + goal.heuristic(neighbor), counter, neighbor)
                )

    raise PlanNotFound(expanded, exhausted=True)


def _reconstruct(
    came_from: dict[WorldState, tuple[WorldState, Action]], state: WorldState
) -> list[Action]:
    actions: list[Action] = []
    while state in came_from:
        state, action = came_from[state]
        actions.append(action)
    actions.reverse()
    return actions
