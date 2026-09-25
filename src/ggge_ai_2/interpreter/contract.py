from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from ggge_ai_2.stream.contract import Frame


@dataclass(frozen=True)
class Situation:
    frame_seq: int
    screen: str
    overlays: frozenset[str] = frozenset()
    map_mode: str | None = None


@dataclass(frozen=True)
class Fact:
    kind: str
    params: Mapping[str, object] = field(default_factory=dict)


class Verdict(StrEnum):
    HOLDS = "holds"
    DOES_NOT_HOLD = "does_not_hold"
    UNREADABLE = "unreadable"


class Interpreter(Protocol):
    def interpret(self, frame: Frame) -> Situation | None: ...

    def verify(self, frame: Frame, fact: Fact) -> Verdict:
        """Check one fact on this frame only.

        Do not ask for a fact that the frame cannot show. A fact that needs more than
        one screen is the work of the agent, over more than one cycle.
        """
        ...
