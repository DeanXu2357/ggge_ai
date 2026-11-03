from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from ggge_ai_2.uisim.contract import RatioRect, UiScreen


class Gesture(StrEnum):
    TAP = "tap"
    LONG_PRESS = "long_press"
    SWIPE_X = "swipe_x"
    SWIPE_Y = "swipe_y"


@dataclass(frozen=True)
class Target:
    screen: UiScreen
    group: str | None = None


@dataclass(frozen=True)
class Transition:
    button: str
    rect: RatioRect | None
    targets: tuple[Target, ...]
    deadline: float
    gesture: Gesture = Gesture.TAP


@dataclass(frozen=True)
class AutoButton:
    button: str
    rect: RatioRect
    deadline: float


@dataclass(frozen=True)
class ScreenChart:
    transitions: tuple[Transition, ...] = ()
    auto: AutoButton | None = None
    waits: tuple[Target, ...] = ()
    danger: tuple[RatioRect, ...] = ()


@dataclass(frozen=True)
class Group:
    name: str
    entry: frozenset[UiScreen]
    members: frozenset[UiScreen]


@dataclass(frozen=True)
class Chart:
    screens: Mapping[UiScreen, ScreenChart]
    groups: tuple[Group, ...]
