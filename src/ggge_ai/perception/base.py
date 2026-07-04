from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

ScreenId = str
UNKNOWN_SCREEN: ScreenId = "unknown"


@dataclass(frozen=True)
class Bbox:
    x: int
    y: int
    w: int
    h: int

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)


@dataclass
class UiElement:
    id: str
    bbox: Bbox
    confidence: float
    text: str | None = None


@dataclass
class BattleUnit:
    id: str
    side: str  # "ally" | "enemy"
    cell: tuple[int, int] | None
    hp_ratio: float | None
    acted: bool | None


@dataclass
class BattleState:
    my_turn: bool
    units: list[BattleUnit] = field(default_factory=list)

    @property
    def enemies_alive(self) -> int:
        return sum(1 for u in self.units if u.side == "enemy")


@dataclass
class GameState:
    screen: ScreenId
    screen_confidence: float
    elements: list[UiElement] = field(default_factory=list)
    battle: BattleState | None = None
    screenshot_path: Path | None = None

    def find_element(self, element_id: str) -> UiElement | None:
        return next((e for e in self.elements if e.id == element_id), None)


class Perception(Protocol):
    def observe(self) -> GameState: ...
