"""BattleState: the single unified board for one battle.

Board knowledge that used to be scattered across the tactical map,
controller-private fields and the ledger is consolidated here into one
world-state object: per-unit entries (faction, world position, numeric HP
and EN, acted flag, bound capabilities) plus global predicates (turn
number, roster verification, third-party controllability). Perception
fills it in incrementally, the planner only reads it, and the ledger takes
snapshots from it (docs/agent-architecture.md, tactical layer).

Every field is optional by design. Current vision only yields an HP-arc
position and a faction; numeric HP and EN wait on panel OCR (issue #9).
Consumers must degrade gracefully on missing values rather than assume
them -- an absent HP is "unknown", never "full" or "zero".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..domain.roster import UnitCapability

Point = tuple[float, float]


class Faction(Enum):
    ALLY = "ally"
    ENEMY = "enemy"
    THIRD_PARTY = "third_party"


class ThirdPartyControl(Enum):
    """Whether this stage lets us drive the third-party force.

    Probed at battle start by selecting such a unit and seeing if its
    action menu opens (docs/agent-architecture.md).
    """

    UNKNOWN = "unknown"
    CONTROLLABLE = "controllable"
    UNCONTROLLABLE = "uncontrollable"


@dataclass
class UnitState:
    """One unit on the board. Faction is the only always-known field;
    everything else is filled in as perception reaches it."""

    unit_id: str
    faction: Faction
    world_pos: Point | None = None
    hp: int | None = None
    max_hp: int | None = None
    en: int | None = None
    acted: bool = False
    capabilities: list[UnitCapability] = field(default_factory=list)

    @property
    def hp_known(self) -> bool:
        return self.hp is not None


@dataclass
class BattleState:
    """The whole board plus global predicates for one battle."""

    units: list[UnitState] = field(default_factory=list)
    turn: int = 1
    roster_verified: bool = False
    third_party_control: ThirdPartyControl = ThirdPartyControl.UNKNOWN

    def add_unit(self, unit: UnitState) -> UnitState:
        self.units.append(unit)
        return unit

    def unit(self, unit_id: str) -> UnitState | None:
        for u in self.units:
            if u.unit_id == unit_id:
                return u
        return None

    def by_faction(self, faction: Faction) -> list[UnitState]:
        return [u for u in self.units if u.faction is faction]

    def allies(self) -> list[UnitState]:
        return self.by_faction(Faction.ALLY)

    def enemies(self) -> list[UnitState]:
        return self.by_faction(Faction.ENEMY)

    def third_party(self) -> list[UnitState]:
        return self.by_faction(Faction.THIRD_PARTY)
