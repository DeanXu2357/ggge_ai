from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ggge_ai_2.uisim.contract import RatioRect


@dataclass(frozen=True)
class ButtonDef:
    name: str
    to: tuple[str, ...]
    rect: RatioRect | None
    gesture: str | None
    dynamic: bool
    forbidden: bool
    deadline: float


@dataclass(frozen=True)
class ScreenDef:
    name: str
    kind: str
    control: str
    buttons: tuple[ButtonDef, ...]
    game_to: tuple[str, ...]


@dataclass(frozen=True)
class CallerGroup:
    name: str
    entry: tuple[str, ...]
    inside: tuple[str, ...]


@dataclass(frozen=True)
class Stages:
    screens: Mapping[str, ScreenDef]
    groups: Mapping[str, CallerGroup]


def load_stages(path: Path) -> Stages:
    data = json.loads(path.read_text(encoding="utf-8"))
    screens = (_screen(raw) for raw in data["screens"])
    groups = (_group(name, raw) for name, raw in data["caller_groups"].items())
    return Stages(
        screens={screen.name: screen for screen in screens},
        groups={group.name: group for group in groups},
    )


def _screen(raw: Any) -> ScreenDef:
    return ScreenDef(
        name=raw["name"],
        kind=raw["kind"],
        control=raw["control"],
        buttons=tuple(_button(button) for button in raw["buttons"]),
        game_to=tuple(raw.get("game_to", ())),
    )


def _button(raw: Any) -> ButtonDef:
    rect = raw.get("rect")
    return ButtonDef(
        name=raw["name"],
        to=tuple(raw["to"]),
        rect=None if rect is None else RatioRect(*rect),
        gesture=raw.get("gesture"),
        dynamic=raw.get("dynamic", False),
        forbidden=raw.get("forbidden", False),
        deadline=float(raw["deadline"]),
    )


def _group(name: str, raw: Any) -> CallerGroup:
    return CallerGroup(name=name, entry=tuple(raw["entry"]), inside=tuple(raw["inside"]))
