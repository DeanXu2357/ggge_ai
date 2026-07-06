"""SimState and step(): the offline, mechanism-only battle transition.

This is the search-tree back end for the expectiminimax solver
(docs/agent-architecture.md, "battle simulator and expectiminimax"). It is a
grid-board mirror of BattleState with the dynamic per-unit fields a forward
search needs (HP/EN, acted flag, re-activation and support charges, movement
range and a weapon list) plus the phase and turn counter. Everything is
parametrised: no stage or unit number is baked in -- callers build SimUnit /
SimWeapon from perception or cache and pass a SimParams for the mechanism
multipliers, which default to the constants in formulas.py.

Geometry (v0): cells are integer (col, row) tuples and distance is the
Chebyshev metric (king moves; a diagonal step costs the same as an orthogonal
one). Weapon reach is a [range_min, range_max] band on that distance. Support
defence is approximated as "a same-faction ally with an unused support charge
sits within its own movement range of the defender". Path blocking is
deferred to v1: movement legality is funnelled through a single replaceable
MoveValidator so a collision-aware version can drop in without touching step.

step(state, decision) returns a fresh SimState and never mutates the input --
clone() is cheap enough to expand a node per call. A decision covers one
unit's activation during its own phase, or, when it carries a DefenseResponse,
the defender's reaction to an incoming attack (the reaction is a decision
point the solver optimises, not an automatic resolution).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import Enum

from . import formulas
from .actions import ActionKind
from .state import Faction

Cell = tuple[int, int]


class Phase(Enum):
    ALLY = "ally"
    THIRD_PARTY = "third_party"
    ENEMY = "enemy"


PHASE_ORDER: tuple[Phase, ...] = (Phase.ALLY, Phase.THIRD_PARTY, Phase.ENEMY)

_PHASE_FACTION: dict[Phase, Faction] = {
    Phase.ALLY: Faction.ALLY,
    Phase.THIRD_PARTY: Faction.THIRD_PARTY,
    Phase.ENEMY: Faction.ENEMY,
}


class DefenseKind:
    NONE = "none"
    DODGE = "dodge"
    DEFEND = "defend"
    SHIELD = "shield"
    COUNTER = "counter"
    SUPPORT_DEFEND = "support_defend"


@dataclass(frozen=True)
class SimParams:
    """Mechanism multipliers, defaulting to the formulas.py constants."""

    defend_multiplier: float = formulas.DEFEND_MULTIPLIER
    shield_multiplier: float = formulas.SHIELD_MULTIPLIER
    support_defend_multiplier: float = 0.5
    dodge_hit_penalty: float = 20.0
    terrain: float = 1.0


DEFAULT_PARAMS = SimParams()


@dataclass(frozen=True)
class SimWeapon:
    """One weapon: reach band, cost and combat numbers, all content."""

    name: str
    power: float
    range_min: int = 1
    range_max: int = 1
    en_cost: int = 0
    accuracy: float = 0.0
    can_counter: bool = True


@dataclass
class SimUnit:
    """A unit on the grid board with the search's dynamic fields."""

    unit_id: str
    faction: Faction
    pos: Cell = (0, 0)
    hp: int = 1
    max_hp: int = 1
    en: int = 0
    en_max: int = 0
    unit_attack: float = 0.0
    unit_defense: float = 0.0
    pilot_attack: float = 0.0
    pilot_defense: float = 0.0
    reaction: float = 0.0
    mobility: float = 0.0
    move_range: int = 0
    weapons: list[SimWeapon] = field(default_factory=list)
    acted: bool = False
    react_charges: int = 0
    react_charges_max: int = 0
    support_charges: int = 0
    support_charges_max: int = 0

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def weapon(self, name: str | None) -> SimWeapon | None:
        if name is None:
            return self.weapons[0] if self.weapons else None
        for w in self.weapons:
            if w.name == name:
                return w
        return None

    def clone(self) -> SimUnit:
        return replace(self, weapons=list(self.weapons))


@dataclass
class DefenseResponse:
    """The defender's reaction to an incoming attack (a decision point)."""

    kind: str = DefenseKind.NONE
    weapon: str | None = None


@dataclass
class Decision:
    """One unit's activation, or (with defense set) a defence reaction.

    hit / counter_hit carry the chance outcome the solver branches on: None
    means "no roll / treated as landing"; the solver sets them explicitly to
    expand a chance node's hit and miss children.
    """

    unit_id: str
    kind: str
    move_to: Cell | None = None
    target_id: str | None = None
    weapon: str | None = None
    amount: float | None = None
    defense: DefenseResponse | None = None
    hit: bool | None = None
    counter_hit: bool | None = None


@dataclass
class SimState:
    """The grid board plus phase/turn, cheap to clone for node expansion."""

    units: list[SimUnit] = field(default_factory=list)
    phase: Phase = Phase.ALLY
    turn: int = 1

    def add_unit(self, unit: SimUnit) -> SimUnit:
        self.units.append(unit)
        return unit

    def unit(self, unit_id: str | None) -> SimUnit | None:
        if unit_id is None:
            return None
        for u in self.units:
            if u.unit_id == unit_id:
                return u
        return None

    def by_faction(self, faction: Faction) -> list[SimUnit]:
        return [u for u in self.units if u.faction is faction and u.alive]

    def allies(self) -> list[SimUnit]:
        return self.by_faction(Faction.ALLY)

    def enemies(self) -> list[SimUnit]:
        return self.by_faction(Faction.ENEMY)

    def clone(self) -> SimState:
        return SimState(
            units=[u.clone() for u in self.units],
            phase=self.phase,
            turn=self.turn,
        )

    def phase_index(self) -> int:
        """Monotonic phase counter; difference = phase boundaries crossed."""
        return self.turn * len(PHASE_ORDER) + PHASE_ORDER.index(self.phase)

    def key(self) -> tuple:
        """Hashable transposition-table key over the whole board."""
        units = tuple(
            sorted(
                (
                    u.unit_id,
                    u.faction.value,
                    u.pos,
                    u.hp,
                    u.en,
                    u.acted,
                    u.react_charges,
                    u.support_charges,
                )
                for u in self.units
            )
        )
        return (self.phase.value, self.turn, units)


# A move is legal when the destination is reachable. v0 default: within the
# unit's movement range on the Chebyshev metric and not standing on another
# living unit. Path blocking (enemies obstructing the route) is v1; swap this
# callable to add it without touching step().
MoveValidator = Callable[["SimState", "SimUnit", Cell], bool]


def chebyshev(a: Cell, b: Cell) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def default_move_validator(state: SimState, unit: SimUnit, dest: Cell) -> bool:
    if chebyshev(unit.pos, dest) > unit.move_range:
        return False
    for other in state.units:
        if other is unit or not other.alive:
            continue
        if other.pos == dest:
            return False
    return True


def move_toward(src: Cell, dst: Cell, steps: int) -> Cell:
    dx = (dst[0] > src[0]) - (dst[0] < src[0])
    dy = (dst[1] > src[1]) - (dst[1] < src[1])
    nx = src[0] + dx * min(steps, abs(dst[0] - src[0]))
    ny = src[1] + dy * min(steps, abs(dst[1] - src[1]))
    return (nx, ny)


def approach(src: Cell, dst: Cell, move_range: int, rmin: int, rmax: int) -> Cell | None:
    """A destination that puts dst inside [rmin, rmax] of the mover, or None.

    v0 only closes distance (does not back away when already too close).
    """
    d = chebyshev(src, dst)
    if rmin <= d <= rmax:
        return src
    if d < rmin:
        return None
    need = d - rmax
    dest = move_toward(src, dst, min(move_range, need))
    nd = chebyshev(dest, dst)
    if rmin <= nd <= rmax:
        return dest
    return None


def opposing_faction(faction: Faction) -> Faction:
    return Faction.ENEMY if faction is Faction.ALLY else Faction.ALLY


def targets_of(state: SimState, unit: SimUnit) -> list[SimUnit]:
    return state.by_faction(opposing_faction(unit.faction))


def legal_attacks(
    state: SimState,
    unit: SimUnit,
    *,
    move_validator: MoveValidator | None = None,
) -> list[Decision]:
    """Attack decisions for a unit: each reachable target x usable weapon."""
    validate = move_validator or default_move_validator
    out: list[Decision] = []
    for target in targets_of(state, unit):
        for weapon in unit.weapons:
            if unit.en < weapon.en_cost:
                continue
            dest = approach(
                unit.pos, target.pos, unit.move_range, weapon.range_min, weapon.range_max
            )
            if dest is None:
                continue
            if dest != unit.pos and not validate(state, unit, dest):
                continue
            out.append(
                Decision(
                    unit_id=unit.unit_id,
                    kind=ActionKind.ATTACK,
                    move_to=None if dest == unit.pos else dest,
                    target_id=target.unit_id,
                    weapon=weapon.name,
                )
            )
    return out


def standby(unit_id: str) -> Decision:
    return Decision(unit_id=unit_id, kind=ActionKind.STANDBY)


def _current_faction(state: SimState) -> Faction:
    return _PHASE_FACTION[state.phase]


def _pending(state: SimState, faction: Faction) -> list[SimUnit]:
    return [u for u in state.units if u.faction is faction and u.alive and not u.acted]


def _begin_phase(state: SimState, faction: Faction) -> None:
    for u in state.units:
        if u.faction is faction:
            u.acted = False
            u.react_charges = u.react_charges_max
            u.support_charges = u.support_charges_max


def _rotate_one(state: SimState) -> None:
    idx = PHASE_ORDER.index(state.phase)
    nxt = PHASE_ORDER[(idx + 1) % len(PHASE_ORDER)]
    if nxt is Phase.ALLY:
        state.turn += 1
    state.phase = nxt
    _begin_phase(state, _PHASE_FACTION[nxt])


def _advance_until_pending(state: SimState) -> None:
    guard = 0
    while not _pending(state, _current_faction(state)) and guard <= len(PHASE_ORDER):
        _rotate_one(state)
        guard += 1


def _remove_dead(state: SimState) -> None:
    state.units = [u for u in state.units if u.alive]


def _defense_multiplier(
    state: SimState,
    defender: SimUnit,
    response: DefenseResponse | None,
    params: SimParams,
) -> float:
    if response is None:
        return formulas.NO_DEFENSE_MULTIPLIER
    kind = response.kind
    if kind == DefenseKind.DEFEND:
        return params.defend_multiplier
    if kind == DefenseKind.SHIELD:
        return params.shield_multiplier
    if kind == DefenseKind.SUPPORT_DEFEND:
        supporter = _find_supporter(state, defender)
        if supporter is None:
            return formulas.NO_DEFENSE_MULTIPLIER
        supporter.support_charges -= 1
        return params.support_defend_multiplier
    return formulas.NO_DEFENSE_MULTIPLIER


def _find_supporter(state: SimState, defender: SimUnit) -> SimUnit | None:
    for u in state.units:
        if u is defender or not u.alive or u.faction is not defender.faction:
            continue
        if u.support_charges <= 0:
            continue
        if chebyshev(u.pos, defender.pos) <= u.move_range:
            return u
    return None


def compute_damage(
    attacker: SimUnit,
    defender: SimUnit,
    weapon: SimWeapon,
    defense_multiplier: float,
    params: SimParams,
) -> int:
    dmg = formulas.expected_damage(
        weapon.power,
        attacker.pilot_attack,
        defender.pilot_defense,
        attacker.unit_attack,
        defender.unit_defense,
        terrain=params.terrain,
        defense_multiplier=defense_multiplier,
    )
    return int(round(dmg))


def _counter_weapon(
    defender: SimUnit, name: str | None, attacker: SimUnit
) -> SimWeapon | None:
    dist = chebyshev(defender.pos, attacker.pos)
    candidates = defender.weapons if name is None else [w for w in defender.weapons if w.name == name]
    for w in candidates:
        if not w.can_counter:
            continue
        if defender.en < w.en_cost:
            continue
        if w.range_min <= dist <= w.range_max:
            return w
    return None


def _apply_attack(
    state: SimState, actor: SimUnit, decision: Decision, params: SimParams
) -> bool:
    """Resolve an attack; return True if it killed the target (grants re-act)."""
    target = state.unit(decision.target_id)
    if target is None or not target.alive:
        return False
    weapon = actor.weapon(decision.weapon)
    if weapon is None or actor.en < weapon.en_cost:
        return False
    dist = chebyshev(actor.pos, target.pos)
    if not (weapon.range_min <= dist <= weapon.range_max):
        return False

    actor.en -= weapon.en_cost
    hit = True if decision.hit is None else decision.hit
    killed = False
    if hit:
        mult = _defense_multiplier(state, target, decision.defense, params)
        target.hp -= compute_damage(actor, target, weapon, mult, params)
        if not target.alive:
            killed = True

    if (
        decision.defense is not None
        and decision.defense.kind == DefenseKind.COUNTER
        and target.alive
    ):
        _apply_counter(state, target, actor, decision, params)

    return killed


def _apply_counter(
    state: SimState,
    defender: SimUnit,
    attacker: SimUnit,
    decision: Decision,
    params: SimParams,
) -> None:
    weapon = _counter_weapon(defender, decision.defense.weapon if decision.defense else None, attacker)
    if weapon is None:
        return
    defender.en -= weapon.en_cost
    hit = True if decision.counter_hit is None else decision.counter_hit
    if hit:
        attacker.hp -= compute_damage(defender, attacker, weapon, 1.0, params)


def _apply_skill(actor: SimUnit, state: SimState, decision: Decision) -> None:
    target = state.unit(decision.target_id) or actor
    if decision.kind == ActionKind.SKILL_EN_REFILL:
        amount = decision.amount if decision.amount is not None else target.en_max
        target.en = min(target.en_max, target.en + int(amount))
    elif decision.kind == ActionKind.SKILL_HEAL:
        amount = decision.amount if decision.amount is not None else target.max_hp
        target.hp = min(target.max_hp, target.hp + int(amount))


def step(
    state: SimState,
    decision: Decision,
    *,
    move_validator: MoveValidator | None = None,
    params: SimParams = DEFAULT_PARAMS,
) -> SimState:
    """Apply one decision to a copy of state and return the new state."""
    s = state.clone()
    actor = s.unit(decision.unit_id)
    if actor is None or not actor.alive:
        _advance_until_pending(s)
        return s

    if decision.move_to is not None:
        validate = move_validator or default_move_validator
        if validate(s, actor, decision.move_to):
            actor.pos = decision.move_to

    killed = False
    if decision.kind == ActionKind.ATTACK:
        killed = _apply_attack(s, actor, decision, params)
    elif decision.kind in (ActionKind.SKILL_EN_REFILL, ActionKind.SKILL_HEAL):
        _apply_skill(actor, s, decision)

    if killed and actor.alive and actor.react_charges > 0:
        actor.react_charges -= 1
        actor.acted = False
    else:
        actor.acted = True

    _remove_dead(s)
    _advance_until_pending(s)
    return s
