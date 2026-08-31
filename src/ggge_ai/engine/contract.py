"""The battle engine contract in Python (spec: docs/spec/battle-engine-protocol.md).

The Go packages 'engine/protocol' and 'engine/battle' hold the same names. A
change here needs the same change there.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

PROTOCOL_VERSION = "1.9"

DECLARED_COMMANDS: tuple[str, ...] = (
    "hello",
    "ping",
    "init",
    "deploy_cells",
    "place",
    "roster",
    "reach",
    "actions",
    "response_attacks",
    "act",
    "export",
    "load",
)

Cell = tuple[int, int]


class Faction(StrEnum):
    ALLY = "ally"
    ENEMY = "enemy"
    THIRD_PARTY = "third_party"


class ActionKind(StrEnum):
    ATTACK = "attack"
    MAP_ATTACK = "map_attack"
    REPOSITION = "reposition"
    STANDBY = "standby"


class SkillSource(StrEnum):
    PILOT = "pilot"
    CREW = "crew"
    MECH = "mech"


class SkillAffects(StrEnum):
    """A skill that acts on the caster alone carries the value ally, because the
    caster is an ally in its own cell. The enum holds no 'self' value.
    """

    ALLY = "ally"
    ENEMY = "enemy"
    ALL = "all"


class Direction(StrEnum):
    """The heading that turns the cells of a shape. The author writes the cells
    one time, against one base heading, and the direction turns the full set of
    the offsets. 'none' is a shape that needs no heading.
    """

    NONE = "none"
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


class MapWeaponAffects(StrEnum):
    ALLY = "ally"
    ENEMY = "enemy"
    ALL = "all"


class Terrain(StrEnum):
    SPACE = "space"
    ATMOSPHERIC = "atmospheric"
    GROUND = "ground"
    SURFACE = "surface"
    UNDERWATER = "underwater"


class Stance(StrEnum):
    """'none' is the unit that stands and takes the strike. 'shield' is no
    answer of the 'response_attacks' command: the shield of a unit settles
    during the damage, in 'act'.
    """

    DODGE = "dodge"
    DEFEND = "defend"
    COUNTER = "counter"
    NONE = "none"


class ErrorCode(StrEnum):
    UNKNOWN_COMMAND = "unknown_command"
    NOT_IMPLEMENTED = "not_implemented"
    BAD_REQUEST = "bad_request"
    NO_SESSION = "no_session"
    ILLEGAL_STATE = "illegal_state"
    ILLEGAL_ACTION = "illegal_action"


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
class Dice:
    mode: DiceMode
    outcomes: tuple[str, ...] = ()
