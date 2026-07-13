"""BattleState -> SimState bridge: the perception-to-search hand-off.

The unified board (battle.state) speaks world pixels and optional numbers;
the simulator speaks grid cells and required numbers. This module quantizes
world positions onto the cell grid, injects roster capabilities as the
simulator's dynamic fields (KILL_REMOVE -> re-activation charges, skill
capabilities -> the skill inventory, SUPPORT_DEFEND / SUPPORT_ATTACK -> the
matching support-charge pools) and
fills every number the search needs from, in order of authority: the live
BattleState, the per-unit spec (panel OCR or content cache, issues #9/#8),
then the caller-tunable BridgeDefaults. Every fallback to a default is
recorded as a human-readable assumption so the ledger can flag advice that
ran on guessed numbers -- an assumption is never silently equal to a fact.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field

from ..domain.roster import CapabilityType
from .sim import Cell, SimSkill, SimState, SimUnit, SimWeapon
from .actions import ActionKind
from .state import BattleState, Point

_CAPABILITY_SKILL_KIND: dict[CapabilityType, str] = {
    CapabilityType.SKILL_EN_REFILL: ActionKind.SKILL_EN_REFILL,
    CapabilityType.SKILL_HEAL: ActionKind.SKILL_HEAL,
}

_KING_STEPS: tuple[Cell, ...] = (
    (-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1),
)


@dataclass(frozen=True)
class UnitSpec:
    """Combat numbers for one unit, from panel OCR or the content cache.

    None means "not read yet"; the bridge falls back to BridgeDefaults and
    records the assumption.
    """

    max_hp: int | None = None
    en_max: int | None = None
    unit_attack: float | None = None
    unit_defense: float | None = None
    pilot_attack: float | None = None
    pilot_shooting: float | None = None
    pilot_melee: float | None = None
    pilot_defense: float | None = None
    reaction: float | None = None
    mobility: float | None = None
    move_range: int | None = None
    weapons: tuple[SimWeapon, ...] = ()


@dataclass(frozen=True)
class BridgeDefaults:
    """Assumed values when neither perception nor a spec supplies a number.

    These are assumptions, not game content: they exist so the search can
    run before OCR/cache coverage is complete, and every use is reported.
    """

    hp: int = 1000
    en: int = 100
    unit_attack: float = 3000.0
    unit_defense: float = 1000.0
    pilot_attack: float = 3000.0
    pilot_defense: float = 1000.0
    reaction: float = 1000.0
    mobility: float = 1000.0
    move_range: int = 5


@dataclass
class BridgeResult:
    state: SimState
    origin: Point
    cell_size: float
    assumptions: list[str] = field(default_factory=list)

    def to_world(self, cell: Cell) -> Point:
        return (
            self.origin[0] + cell[0] * self.cell_size,
            self.origin[1] + cell[1] * self.cell_size,
        )


def _quantize(world: Point, origin: Point, cell_size: float) -> Cell:
    return (
        round((world[0] - origin[0]) / cell_size),
        round((world[1] - origin[1]) / cell_size),
    )


def _note(assumptions: list[str], uid: str, name: str, value: object) -> None:
    assumptions.append(f"{uid}: {name} unknown, assumed {value}")


def _nearest_free(cell: Cell, taken: set[Cell]) -> Cell:
    seen = {cell}
    frontier = deque([cell])
    while frontier:
        pos = frontier.popleft()
        if pos not in taken:
            return pos
        for dx, dy in _KING_STEPS:
            nxt = (pos[0] + dx, pos[1] + dy)
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    return cell


def build_sim_state(
    battle: BattleState,
    specs: Mapping[str, UnitSpec],
    *,
    cell_size: float,
    defaults: BridgeDefaults | None = None,
) -> BridgeResult:
    defaults = defaults or BridgeDefaults()
    assumptions: list[str] = []
    placed = [u for u in battle.units if u.world_pos is not None]
    for u in battle.units:
        if u.world_pos is None:
            assumptions.append(f"{u.unit_id}: no world position, left out of the simulation")
    if placed:
        origin = (
            min(u.world_pos[0] for u in placed),
            min(u.world_pos[1] for u in placed),
        )
    else:
        origin = (0.0, 0.0)

    state = SimState(turn=battle.turn)
    taken: set[Cell] = set()
    for u in placed:
        cell = _quantize(u.world_pos, origin, cell_size)
        if cell in taken:
            free = _nearest_free(cell, taken)
            assumptions.append(f"{u.unit_id}: cell {cell} occupied, nudged to {free}")
            cell = free
        taken.add(cell)

        spec = specs.get(u.unit_id) or UnitSpec()
        max_hp = u.max_hp if u.max_hp is not None else spec.max_hp
        hp = u.hp
        if hp is None:
            hp = max_hp if max_hp is not None else defaults.hp
            _note(assumptions, u.unit_id, "HP", hp)
        if max_hp is None:
            max_hp = max(hp, defaults.hp)
            _note(assumptions, u.unit_id, "max HP", max_hp)
        en_max = spec.en_max
        en = u.en
        if en is None:
            en = en_max if en_max is not None else defaults.en
            _note(assumptions, u.unit_id, "EN", en)
        if en_max is None:
            en_max = max(en, defaults.en)
            _note(assumptions, u.unit_id, "max EN", en_max)
        if spec.move_range is None:
            _note(assumptions, u.unit_id, "move range", defaults.move_range)
        if not spec.weapons:
            assumptions.append(f"{u.unit_id}: no weapons known, inert in the simulation")

        reacts = 0
        support_defends = 0
        support_attacks = 0
        skills: list[SimSkill] = []
        for cap in u.capabilities:
            if cap.type is CapabilityType.KILL_REMOVE:
                reacts += cap.charges if cap.charges is not None else 1
            elif cap.type is CapabilityType.SUPPORT_DEFEND:
                support_defends += cap.charges if cap.charges is not None else 1
            elif cap.type is CapabilityType.SUPPORT_ATTACK:
                support_attacks += cap.charges if cap.charges is not None else 1
            elif cap.type in _CAPABILITY_SKILL_KIND:
                skills.append(
                    SimSkill(
                        kind=_CAPABILITY_SKILL_KIND[cap.type],
                        uses=cap.charges if cap.charges is not None else 1,
                    )
                )

        state.add_unit(
            SimUnit(
                unit_id=u.unit_id,
                faction=u.faction,
                pos=cell,
                hp=hp,
                max_hp=max_hp,
                en=en,
                en_max=en_max,
                unit_attack=spec.unit_attack if spec.unit_attack is not None else defaults.unit_attack,
                unit_defense=spec.unit_defense if spec.unit_defense is not None else defaults.unit_defense,
                pilot_attack=spec.pilot_attack if spec.pilot_attack is not None else defaults.pilot_attack,
                pilot_defense=spec.pilot_defense if spec.pilot_defense is not None else defaults.pilot_defense,
                reaction=spec.reaction if spec.reaction is not None else defaults.reaction,
                mobility=spec.mobility if spec.mobility is not None else defaults.mobility,
                move_range=spec.move_range if spec.move_range is not None else defaults.move_range,
                weapons=list(spec.weapons),
                skills=skills,
                acted=u.acted,
                react_charges=reacts,
                react_charges_max=reacts,
                support_defend_charges=support_defends,
                support_defend_charges_max=support_defends,
                support_attack_charges=support_attacks,
                support_attack_charges_max=support_attacks,
            )
        )
    return BridgeResult(
        state=state, origin=origin, cell_size=cell_size, assumptions=assumptions
    )
