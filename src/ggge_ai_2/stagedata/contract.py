from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

import numpy as np

# A stage cell is (column, row) on the whole map: (0, 0) is the top-left cell of the map.
StageCell = tuple[int, int]


class Terrain(StrEnum):
    SPACE = "space"
    ATMOSPHERIC = "atmospheric"
    GROUND = "ground"
    SURFACE = "surface"
    UNDERWATER = "underwater"


class Faction(StrEnum):
    ALLY = "ally"
    ENEMY = "enemy"


class UnitRole(StrEnum):
    ATTACK = "attack"
    ENDURANCE = "endurance"
    SUPPORT = "support"
    # Only the NPC units of the system have this role.
    NO_ROLE = "no_role"


class PilotState(StrEnum):
    NORMAL = "一般"
    STRONG = "強勢"
    SUPER_STRONG = "超強勢"
    SUPER_STRIKE = "超一擊"


# Two crops of one name differ in some pixels, so compare two masks by their
# similarity. Equality is identity.
@dataclass(frozen=True, eq=False)
class NameMask:
    mask: np.ndarray


@dataclass(frozen=True)
class UnitBrief:
    mech_role: UnitRole
    mech_name: NameMask
    hp: int
    en: int
    pilot_role: UnitRole
    pilot_name: NameMask
    mp: int
    mp_max: int
    state: PilotState


@dataclass(frozen=True)
class UnitDetail:
    pass


@dataclass(frozen=True)
class StageUnit:
    pos: StageCell
    size: tuple[int, int]
    faction: Faction
    controllable: bool
    brief: UnitBrief
    detail: UnitDetail


@dataclass(frozen=True)
class VictoryCondition:
    pass


@dataclass(frozen=True)
class StageEvent:
    pass


@dataclass(frozen=True)
class StageData:
    stage: str
    # A game update can change a stage, so the data of two app versions of one stage
    # live side by side.
    app_version: str
    # The first 8 characters of the git commit of the code that surveyed the stage.
    code_version: str
    columns: int
    rows: int
    # Each cell holds the terrains that a unit can take on it.
    terrain: Mapping[StageCell, frozenset[Terrain]]
    # The stage does not fix the sortie, so the data keeps the cells where the sortie
    # units start, and 'units' holds only the units that the stage fixes. The game gives
    # the cells to the sortie slots in this order.
    deploy_cells: tuple[StageCell, ...]
    units: tuple[StageUnit, ...]
    victory: tuple[VictoryCondition, ...]
    events: tuple[StageEvent, ...]


class StageStore(Protocol):
    def load(self, stage: str, app_version: str) -> StageData | None:
        """Return None when the store has no data of this app version of the stage."""
        ...

    def save(self, data: StageData) -> None: ...
