"""內層 goal：勝利條件型別＋主動離場。全滅型是批 1a 唯一實作的一種。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from .state import Cell, StageState


class Goal(ABC):
    """unmet 是 A* 啟發式的原料：未滿足的目標事實個數。

    容許性由規劃層的 min_action_cost 保證，goal 本身不做尺度假設。
    """

    name: ClassVar[str]

    @abstractmethod
    def is_satisfied(self, state: StageState) -> bool: ...

    @abstractmethod
    def unmet(self, state: StageState) -> int: ...


@dataclass(frozen=True)
class Annihilation(Goal):
    name: ClassVar[str] = "annihilation"

    def is_satisfied(self, state: StageState) -> bool:
        return not state.enemies

    def unmet(self, state: StageState) -> int:
        return len(state.enemies)


@dataclass(frozen=True)
class DestroyTargets(Goal):
    """勝利條件型別位置：擊破特定目標。批 1a 不實作。"""

    name: ClassVar[str] = "destroy_targets"
    targets: frozenset[str]

    def is_satisfied(self, state: StageState) -> bool:
        raise NotImplementedError("批 5：goal 全規格")

    def unmet(self, state: StageState) -> int:
        raise NotImplementedError("批 5：goal 全規格")


@dataclass(frozen=True)
class ReachLocation(Goal):
    """勝利條件型別位置：指定或任意單位到達指定地點。批 1a 不實作。"""

    name: ClassVar[str] = "reach_location"
    destination: Cell
    unit: str | None = None

    def is_satisfied(self, state: StageState) -> bool:
        raise NotImplementedError("批 5：goal 全規格")

    def unmet(self, state: StageState) -> int:
        raise NotImplementedError("批 5：goal 全規格")


@dataclass(frozen=True)
class LeftStage(Goal):
    name: ClassVar[str] = "left_stage"

    def is_satisfied(self, state: StageState) -> bool:
        return state.withdrawn

    def unmet(self, state: StageState) -> int:
        return 0 if state.withdrawn else 1
