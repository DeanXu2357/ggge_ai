from __future__ import annotations

from dataclasses import dataclass

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
