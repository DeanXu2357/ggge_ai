"""The battle engine contract in Python (spec: docs/spec/battle-engine-protocol.md).

The Go package 'engine/protocol' holds the same names. A change here needs the
same change there.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

PROTOCOL_VERSION = "1.0"

DECLARED_COMMANDS: tuple[str, ...] = (
    "hello",
    "ping",
    "init",
    "deploy_cells",
    "place",
    "roster",
    "reach",
    "actions",
    "reactions",
    "act",
    "rollback",
    "set_unit",
    "advice",
    "certify",
    "export",
    "load",
)

Cell = tuple[int, int]


class ErrorCode(StrEnum):
    UNKNOWN_COMMAND = "unknown_command"
    NOT_IMPLEMENTED = "not_implemented"
    BAD_REQUEST = "bad_request"
    NO_SESSION = "no_session"
    ILLEGAL_STATE = "illegal_state"
    ILLEGAL_ACTION = "illegal_action"
    EMPTY_HISTORY = "empty_history"


class Guarantee(StrEnum):
    KILL = "kill"
    NONE = "none"


class VictoryKind(StrEnum):
    DESTROY_ALL = "destroy_all"
    DESTROY_TARGET = "destroy_target"
    REACH_CELL = "reach_cell"


class DiceMode(StrEnum):
    FORCED = "forced"
    SAMPLED = "sampled"


@dataclass(frozen=True)
class Victory:
    kind: VictoryKind
    target_id: str | None = None
    cell: Cell | None = None


@dataclass(frozen=True)
class Score:
    survive_all: bool = False
    hp_floor: int = 0


@dataclass(frozen=True)
class Goal:
    victory: tuple[Victory, ...]
    score: Score = Score()


@dataclass(frozen=True)
class Budget:
    time_ms: int = 0
    nodes: int = 0


@dataclass(frozen=True)
class Dice:
    mode: DiceMode
    outcomes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Verdict:
    """A guarantee of NONE says that the engine holds no certificate. It does
    not say that the action fails."""

    action: Any
    expected_value: float
    guarantee: Guarantee
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Verdict:
        return cls(
            action=payload.get("action"),
            expected_value=float(payload.get("expected_value", 0.0)),
            guarantee=Guarantee(payload.get("guarantee", Guarantee.NONE)),
            diagnostics=dict(payload.get("diagnostics") or {}),
        )
