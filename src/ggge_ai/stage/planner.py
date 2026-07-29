"""GOAP A*。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .actions import Action


def plan(
    state: Mapping[str, Any], goal: Mapping[str, Any], actions: Sequence[Action]
) -> tuple[Action, ...]:
    raise NotImplementedError("批 1：內層離線")
