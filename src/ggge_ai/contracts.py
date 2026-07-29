"""跨層資料契約（規格：docs/module-map.md）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Objective(Enum):
    CLEAR = "clear"
    SCORE = "score"
    ACHIEVEMENT = "achievement"
    HIDDEN = "hidden"


class Constraint(Enum):
    SPLIT = "split"
    SINGLE = "single"


class HiddenPolicy(Enum):
    ENTER = "enter"
    DECLINE = "decline"


class Ending(Enum):
    VICTORY = "victory"
    DEFEAT = "defeat"
    STUCK = "stuck"
    WITHDREW = "withdrew"


@dataclass(frozen=True)
class GoalSpec:
    stage: str
    objectives: frozenset[Objective]
    constraint: Constraint


@dataclass(frozen=True)
class StageOrder:
    stage: str
    objectives: frozenset[Objective]
    hidden_policy: HiddenPolicy
    max_ticks: int


@dataclass
class IntelDelta:
    """情報增量佔位；欄位隨批 1 內層情報記錄定案（module-map 待辦 6）。"""

    facts: dict[str, Any] = field(default_factory=dict)


@dataclass
class StageReport:
    stage: str
    ending: Ending
    achieved: dict[Objective, bool]
    reason: str = ""
    intel: IntelDelta = field(default_factory=IntelDelta)


@dataclass(frozen=True)
class Bottleneck:
    """kind 是字串佔位：瓶頸分類法未定（module-map 待辦 4）。"""

    kind: str
    gap: float


@dataclass(frozen=True)
class Diagnosis:
    win_rate: float
    bottlenecks: tuple[Bottleneck, ...] = ()
