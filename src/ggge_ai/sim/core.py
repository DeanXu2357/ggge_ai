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
eligibility is approximated as "a same-faction ally with an unused charge of
the matching kind sits within its own movement range of the defender". Path
blocking is deferred to v1: movement legality is funnelled through a single
replaceable MoveValidator so a collision-aware version can drop in without
touching step.

Engagement resolution follows the live game's order (user-observed cases and
the case-by-case Q&A, 2026-07-13, recorded in docs/combat-formulas.md):

  1. the attacking side strikes, support volley first, then the main
     attacker (support units carry debuffs the later strikes must benefit
     from). When the response asks for interception and an eligible support
     defender exists, *every* strike of the volley lands on the interceptor
     -- a first strike destroying it does not let the rest punch through to
     the target. Damage is computed against the struck unit's own stats. At
     most one interceptor per engagement (which one is the game AI's pick;
     board order stands in here), one interception charge per engagement,
     and only a landed hit spends it -- an all-miss volley spares it.
  2. the struck unit's death resolves immediately; a destroyed interceptor
     cancels nothing that follows, and an engagement kill grants the main
     attacker's re-activation whether target or interceptor fell (provided
     the attacker survives the counter phase and has charges left -- step()
     already checks both).
  3. the counter phase fires only while the *target* is alive: the
     defender-side support volley first, then the target's counter (stance
     COUNTER); strikes stop once the attacker is destroyed. Support fire
     only needs the foe inside the supporter's weapon reach and a remaining
     charge -- it does not care whether the target itself can counter. A
     target killed in step 2 cancels the whole counter phase, confirmed in
     both directions.

Support eligibility is confirmed mechanism, not approximation: the ability
is a pilot trait, and the protected/assisted ally must sit within the
supporter's own movement range; the weapon must reach the foe. Volleys cap
at max_support_attackers (live limit 3 or 4, web check pending).

Q&A round three confirmed more of the model as-is: an engagement kill
grants the main attacker's re-activation no matter whose strike landed the
blow; re-activation is a full activation reset (move, attack, skill, MAP
weapon alike -- acted=False is faithful); counters are unlimited within a
phase (EN and survival are the only gates, which makes counter-bait lines
legitimate); the counter only ever targets the main attacker; and counters
and support fire pay their weapon's EN with cheaper weapons as fallback.

Defender-side decisions (stance, interception, support fire and its weapon)
are all player choices in the live game -- the popup merely pre-fills
defaults -- so the solver optimising over them is faithful; the offense
volley rides Decision.support and the solver enumerates both settings when
a teammate holds a charge. Mechanism landed ahead of its content feeds
(fields default off until panels/abilities supply them): attack_shield
(issue #22), interception_reduction (issue #20), has_shield, MAP weapons
(SimWeapon.map_weapon + per-unit weapon_ammo), weapon debuffs (SimDebuff:
applied on a landed strike, one full round crossing from the enemy phase
into ours, larger same-kind magnitude overwrites -- a damage-taken
multiplier channel in v0), and the confirmed 10% per-phase EN regen. Not
yet modelled: per-strike support hit% (readable on the forecast; treated
as landing). Committed strikes not retargeting a mid-volley kill remains
an assumption.

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
from .vocab import DecisionKind, Faction

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


DEFENSE_STANCES: tuple[str, ...] = (
    DefenseKind.NONE,
    DefenseKind.DODGE,
    DefenseKind.DEFEND,
    DefenseKind.SHIELD,
    DefenseKind.COUNTER,
)


@dataclass(frozen=True)
class SimParams:
    """Mechanism multipliers, defaulting to the formulas.py constants.

    Interception damage follows community sources (2026-07-13 web research,
    issue #20): the interceptor takes the hit in its defend stance --
    support_defend_multiplier (0.8) normally, shield_multiplier when the
    interceptor has_shield. Whether the two stack (0.48, one "separate
    slots" claim) is the remaining live calibration; per-unit reduction
    traits are content read from panels.

    max_support_attackers caps the simultaneous support-attack volley; no
    community source states the live limit (user recalls 3 or 4), count the
    on-map support marks to settle it. en_regen_fraction is the confirmed
    passive regen: every faction recovers 10% of max EN at the start of its
    own phase (rounding rule unverified; round-half-up assumed).
    """

    defend_multiplier: float = formulas.DEFEND_MULTIPLIER
    shield_multiplier: float = formulas.SHIELD_MULTIPLIER
    support_defend_multiplier: float = formulas.DEFEND_MULTIPLIER
    dodge_hit_penalty: float = 20.0
    terrain: float = 1.0
    max_support_attackers: int = 3
    en_regen_fraction: float = 0.10


DEFAULT_PARAMS = SimParams()


@dataclass(frozen=True)
class SimWeapon:
    """One weapon: reach band, cost and combat numbers, all content.

    map_weapon marks a MAP weapon (settled rules 2026-07-13): aimed at a
    cell inside the reach band, hits every enemy within `blast` Chebyshev
    distance of the aim, always lands, allows no reaction of any kind,
    never hits friendlies, grants no re-activation and force-ends the
    activation. It feeds on the unit's per-weapon ammo (weapon_ammo), which
    EN refills cannot restock. Blast shape per weapon is content; the
    radius is a v0 approximation.
    """

    name: str
    power: float
    range_min: int = 1
    range_max: int = 1
    en_cost: int = 0
    accuracy: float = 0.0
    can_counter: bool = True
    map_weapon: bool = False
    blast: int = 0
    debuff_kind: str | None = None
    debuff_magnitude: float = 0.0


@dataclass
class SimSkill:
    """A usable skill in the unit's inventory (EN refill / heal, content).

    `uses` is the remaining charge count the search decrements. `ends_turn`
    is mechanism: whether firing the skill consumes the activation -- the
    real value is read from the game per skill; True is the conservative
    default. `amount` None means "restore to full".
    """

    kind: str
    amount: float | None = None
    uses: int = 1
    ends_turn: bool = True


@dataclass(frozen=True)
class SimDebuff:
    """An active debuff on a unit: content magnitude, mechanism lifetime.

    Lives one full round (settled 2026-07-13): applied during phase P it
    stays through every other phase and expires when a phase of P's kind
    next begins. Same kind: the larger magnitude overwrites; different
    kinds coexist. v0 channel: a damage-taken multiplier (formula slot 9).
    """

    kind: str
    magnitude: float
    applied_index: int


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
    skills: list[SimSkill] = field(default_factory=list)
    acted: bool = False
    react_charges: int = 0
    react_charges_max: int = 0
    support_defend_charges: int = 0
    support_defend_charges_max: int = 0
    support_attack_charges: int = 0
    support_attack_charges_max: int = 0
    has_shield: bool = False
    attack_shield: bool = False
    interception_reduction: float = 0.0
    weapon_ammo: dict[str, int] = field(default_factory=dict)
    debuffs: list[SimDebuff] = field(default_factory=list)

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
        return replace(
            self,
            weapons=list(self.weapons),
            skills=[replace(s) for s in self.skills],
            weapon_ammo=dict(self.weapon_ammo),
            debuffs=list(self.debuffs),
        )


@dataclass
class DefenseResponse:
    """The defender's reaction to an incoming attack (a decision point).

    kind is the target's own stance. support_defend asks an eligible support
    defender to intercept the strike (independent of the stance: the target
    still counters from behind the interceptor). support_attack lets an
    eligible support attacker join the counter phase; it defaults on because
    the live game fires it without a choice.
    """

    kind: str = DefenseKind.NONE
    weapon: str | None = None
    support_defend: bool = False
    support_attack: bool = True


@dataclass
class Decision:
    """One unit's activation, or (with defense set) a defence reaction.

    support brings eligible own-side support attackers along on an attack
    (offense volley). hit / counter_hit / support_hit carry the chance
    outcome the solver branches on: None means "no roll / treated as
    landing"; the solver sets them explicitly to expand a chance node's hit
    and miss children. support_hit covers both sides' volleys.
    """

    unit_id: str
    kind: str
    move_to: Cell | None = None
    target_id: str | None = None
    weapon: str | None = None
    amount: float | None = None
    defense: DefenseResponse | None = None
    support: bool = True
    aim: Cell | None = None
    hit: bool | None = None
    counter_hit: bool | None = None
    support_hit: bool | None = None


@dataclass(frozen=True)
class SimEvent:
    """A scripted stage event: trigger -> board change, from the stage
    definition file. trigger v1: {"type": "kill", "uid", "within_turn"?}
    or {"type": "turn_start", "turn"}; effect v1: {"type": "spawn",
    "units": [SimUnit templates]} or {"type": "weaken", "uids",
    "attack_multiplier"?, "defense_multiplier"?}. Unknown effect types
    are inert no-ops (validated and noted upstream, never here -- step()
    runs per node). The table itself is static; only which events are
    still pending / already fired lives on SimState."""

    event_id: str
    trigger: dict
    effect: dict


EventTable = dict[str, SimEvent]


@dataclass
class SimState:
    """The grid board plus phase/turn, cheap to clone for node expansion.

    bounds is ((min_x, min_y), (max_x, max_y)) inclusive, or None for an
    unbounded board (v0 behaviour); only the grid-aware validators read it.

    pending_events/fired_events both enter key(): a kill event with a
    within_turn window can *expire* (leave pending without firing), so
    pending alone cannot distinguish "fired" from "expired" -- and a
    fired weaken changes unit statics that key() deliberately omits.
    With both tuples in the key, equal keys imply the same event history
    and therefore the same statics, keeping the TT sound."""

    units: list[SimUnit] = field(default_factory=list)
    phase: Phase = Phase.ALLY
    turn: int = 1
    bounds: tuple[Cell, Cell] | None = None
    pending_events: tuple[str, ...] = ()
    fired_events: tuple[str, ...] = ()

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
            bounds=self.bounds,
            pending_events=self.pending_events,
            fired_events=self.fired_events,
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
                    u.support_defend_charges,
                    u.support_attack_charges,
                    tuple(sorted(u.weapon_ammo.items())),
                    tuple(sorted((d.kind, d.magnitude, d.applied_index) for d in u.debuffs)),
                    tuple(s.uses for s in u.skills),
                )
                for u in self.units
            )
        )
        return (self.phase.value, self.turn, self.pending_events, self.fired_events, units)


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


def legal_map_attacks(state: SimState, unit: SimUnit) -> list[Decision]:
    """MAP-weapon decisions: pre-move only, aimed at each foe's cell in reach."""
    out: list[Decision] = []
    for weapon in unit.weapons:
        if not weapon.map_weapon:
            continue
        if unit.weapon_ammo.get(weapon.name, 0) <= 0 or unit.en < weapon.en_cost:
            continue
        for target in targets_of(state, unit):
            dist = chebyshev(unit.pos, target.pos)
            if weapon.range_min <= dist <= weapon.range_max:
                out.append(
                    Decision(
                        unit_id=unit.unit_id,
                        kind=DecisionKind.MAP_ATTACK,
                        weapon=weapon.name,
                        aim=target.pos,
                    )
                )
    return out


def legal_attacks(
    state: SimState,
    unit: SimUnit,
    *,
    move_validator: MoveValidator | None = None,
    reach: set[Cell] | None = None,
) -> list[Decision]:
    """Attack decisions for a unit: each reachable target x usable weapon.

    `reach` is the unit's path-aware reachable cell set (battle.grid). When
    given it replaces the validator for destination legality and, if the
    straight-line approach is blocked, supplies a detour: the closest
    reachable cell that puts the target inside the weapon band.
    """
    validate = move_validator or default_move_validator
    out: list[Decision] = []
    for target in targets_of(state, unit):
        for weapon in unit.weapons:
            if weapon.map_weapon or unit.en < weapon.en_cost:
                continue
            dest = approach(
                unit.pos, target.pos, unit.move_range, weapon.range_min, weapon.range_max
            )
            if dest is not None and dest != unit.pos:
                if reach is not None:
                    if dest not in reach:
                        dest = None
                elif not validate(state, unit, dest):
                    dest = None
            if dest is None and reach is not None:
                band = [
                    c
                    for c in reach
                    if weapon.range_min <= chebyshev(c, target.pos) <= weapon.range_max
                ]
                if band:
                    dest = min(band, key=lambda c: (chebyshev(unit.pos, c), c))
            if dest is None:
                continue
            out.append(
                Decision(
                    unit_id=unit.unit_id,
                    kind=DecisionKind.ATTACK,
                    move_to=None if dest == unit.pos else dest,
                    target_id=target.unit_id,
                    weapon=weapon.name,
                )
            )
    return out


def standby(unit_id: str) -> Decision:
    return Decision(unit_id=unit_id, kind=DecisionKind.STANDBY)


def legal_skills(unit: SimUnit) -> list[Decision]:
    """Skill decisions that would change something right now (self-target v0)."""
    out: list[Decision] = []
    for skill in unit.skills:
        if skill.uses <= 0:
            continue
        if skill.kind == DecisionKind.SKILL_EN_REFILL and unit.en < unit.en_max:
            out.append(Decision(unit_id=unit.unit_id, kind=skill.kind, amount=skill.amount))
        elif skill.kind == DecisionKind.SKILL_HEAL and unit.hp < unit.max_hp:
            out.append(Decision(unit_id=unit.unit_id, kind=skill.kind, amount=skill.amount))
    return out


def _first_valid_step(
    state: SimState,
    unit: SimUnit,
    direction_target: Cell,
    validate: MoveValidator,
) -> Cell | None:
    """Longest valid move along the king-move line toward direction_target."""
    for steps in range(unit.move_range, 0, -1):
        dest = move_toward(unit.pos, direction_target, steps)
        if dest != unit.pos and validate(state, unit, dest):
            return dest
    return None


def reposition_moves(
    state: SimState,
    unit: SimUnit,
    *,
    move_validator: MoveValidator | None = None,
) -> list[Decision]:
    """Pure positioning candidates: toward each target, away from the nearest.

    These give the search destinations that matter tactically without
    enumerating every reachable cell: closing distance on out-of-reach
    targets and opening distance from the nearest threat. Standby covers
    holding position.
    """
    validate = move_validator or default_move_validator
    if unit.move_range <= 0:
        return []
    targets = targets_of(state, unit)
    cells: list[Cell] = []
    for target in targets:
        dest = _first_valid_step(state, unit, target.pos, validate)
        if dest is not None:
            cells.append(dest)
    if targets:
        nearest = min(targets, key=lambda t: chebyshev(unit.pos, t.pos))
        sx = (unit.pos[0] > nearest.pos[0]) - (unit.pos[0] < nearest.pos[0])
        sy = (unit.pos[1] > nearest.pos[1]) - (unit.pos[1] < nearest.pos[1])
        if sx == 0 and sy == 0:
            sx = 1
        away = (
            unit.pos[0] + sx * unit.move_range,
            unit.pos[1] + sy * unit.move_range,
        )
        dest = _first_valid_step(state, unit, away, validate)
        if dest is not None:
            cells.append(dest)
    out: list[Decision] = []
    seen: set[Cell] = set()
    for cell in cells:
        if cell in seen:
            continue
        seen.add(cell)
        out.append(Decision(unit_id=unit.unit_id, kind=DecisionKind.MOVE, move_to=cell))
    return out


def _current_faction(state: SimState) -> Faction:
    return _PHASE_FACTION[state.phase]


def _pending(state: SimState, faction: Faction) -> list[SimUnit]:
    return [u for u in state.units if u.faction is faction and u.alive and not u.acted]


def _begin_phase(state: SimState, faction: Faction, params: SimParams) -> None:
    for u in state.units:
        if u.faction is faction:
            u.acted = False
            u.react_charges = u.react_charges_max
            u.support_defend_charges = u.support_defend_charges_max
            u.support_attack_charges = u.support_attack_charges_max
            regen = int(round(u.en_max * params.en_regen_fraction))
            u.en = min(u.en_max, u.en + regen)


def _rotate_one(state: SimState, params: SimParams, events: EventTable | None = None) -> None:
    idx = PHASE_ORDER.index(state.phase)
    nxt = PHASE_ORDER[(idx + 1) % len(PHASE_ORDER)]
    if nxt is Phase.ALLY:
        state.turn += 1
        _events_on_new_turn(state, events)
    state.phase = nxt
    _expire_debuffs(state)
    _begin_phase(state, _PHASE_FACTION[nxt], params)


def _expire_debuffs(state: SimState) -> None:
    now = state.phase_index()
    for u in state.units:
        if u.debuffs:
            u.debuffs = [d for d in u.debuffs if now - d.applied_index < len(PHASE_ORDER)]


def _apply_debuff(state: SimState, weapon: SimWeapon, victim: SimUnit) -> None:
    if weapon.debuff_kind is None:
        return
    existing = next((d for d in victim.debuffs if d.kind == weapon.debuff_kind), None)
    if existing is not None:
        if existing.magnitude >= weapon.debuff_magnitude:
            return
        victim.debuffs.remove(existing)
    victim.debuffs.append(
        SimDebuff(weapon.debuff_kind, weapon.debuff_magnitude, state.phase_index())
    )


def _advance_until_pending(
    state: SimState, params: SimParams, events: EventTable | None = None
) -> None:
    guard = 0
    while not _pending(state, _current_faction(state)) and guard <= len(PHASE_ORDER):
        _rotate_one(state, params, events)
        guard += 1


def _remove_dead(state: SimState) -> None:
    state.units = [u for u in state.units if u.alive]


def _apply_event_effect(state: SimState, event: SimEvent) -> None:
    effect = event.effect
    if effect.get("type") == "spawn":
        for template in effect.get("units", ()):
            if state.unit(template.unit_id) is None:
                state.units.append(template.clone())
    elif effect.get("type") == "weaken":
        for uid in effect.get("uids", ()):
            unit = state.unit(uid)
            if unit is not None:
                unit.unit_attack *= effect.get("attack_multiplier", 1.0)
                unit.unit_defense *= effect.get("defense_multiplier", 1.0)


def _fire_event(state: SimState, event: SimEvent) -> None:
    _apply_event_effect(state, event)
    state.pending_events = tuple(e for e in state.pending_events if e != event.event_id)
    state.fired_events = (*state.fired_events, event.event_id)


def _events_after_step(state: SimState, events: EventTable | None) -> None:
    """Kill triggers: a pending event whose uid is dead or gone fires now
    (dead units are removed from the board, and stage uids are unique, so
    absence means death). A within_turn window past its deadline never
    fires -- expiry happens at turn rotation."""
    if not events:
        return
    for event_id in state.pending_events:
        event = events.get(event_id)
        if event is None or event.trigger.get("type") != "kill":
            continue
        within = event.trigger.get("within_turn")
        if within is not None and state.turn > int(within):
            continue
        victim = state.unit(event.trigger.get("uid"))
        if victim is None or not victim.alive:
            _fire_event(state, event)


def _events_on_new_turn(state: SimState, events: EventTable | None) -> None:
    """At rotation into a new turn: fire turn_start triggers and expire
    kill windows the new turn has passed. Expired events leave pending
    without entering fired -- that difference is exactly why both tuples
    sit in SimState.key()."""
    if not events:
        return
    for event_id in tuple(state.pending_events):
        event = events.get(event_id)
        if event is None:
            continue
        trigger = event.trigger
        if trigger.get("type") == "turn_start" and state.turn >= int(trigger.get("turn", 0)):
            _fire_event(state, event)
        elif trigger.get("type") == "kill":
            within = trigger.get("within_turn")
            if within is not None and state.turn > int(within):
                state.pending_events = tuple(
                    e for e in state.pending_events if e != event_id
                )


def _stance_multiplier(response: DefenseResponse | None, params: SimParams) -> float:
    if response is None:
        return formulas.NO_DEFENSE_MULTIPLIER
    if response.kind == DefenseKind.DEFEND:
        return params.defend_multiplier
    if response.kind == DefenseKind.SHIELD:
        return params.shield_multiplier
    return formulas.NO_DEFENSE_MULTIPLIER


def _interception_multiplier(interceptor: SimUnit, params: SimParams) -> float:
    base = params.shield_multiplier if interceptor.has_shield else params.support_defend_multiplier
    return base * (1.0 - interceptor.interception_reduction)


def find_support_defender(state: SimState, defender: SimUnit) -> SimUnit | None:
    for u in state.units:
        if u is defender or not u.alive or u.faction is not defender.faction:
            continue
        if u.support_defend_charges <= 0:
            continue
        if chebyshev(u.pos, defender.pos) <= u.move_range:
            return u
    return None


def find_support_attackers(
    state: SimState, supported: SimUnit, foe: SimUnit
) -> list[tuple[SimUnit, SimWeapon]]:
    out: list[tuple[SimUnit, SimWeapon]] = []
    for u in state.units:
        if u is supported or not u.alive or u.faction is not supported.faction:
            continue
        if u.support_attack_charges <= 0:
            continue
        if chebyshev(u.pos, supported.pos) > u.move_range:
            continue
        dist = chebyshev(u.pos, foe.pos)
        for w in u.weapons:
            if w.map_weapon:
                continue
            if u.en >= w.en_cost and w.range_min <= dist <= w.range_max:
                out.append((u, w))
                break
    return out


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
    taken = 1.0 + sum(d.magnitude for d in defender.debuffs)
    return int(round(dmg * taken))


def _counter_weapon(
    defender: SimUnit, name: str | None, attacker: SimUnit
) -> SimWeapon | None:
    dist = chebyshev(defender.pos, attacker.pos)
    candidates = defender.weapons if name is None else [w for w in defender.weapons if w.name == name]
    for w in candidates:
        if w.map_weapon or not w.can_counter:
            continue
        if defender.en < w.en_cost:
            continue
        if w.range_min <= dist <= w.range_max:
            return w
    return None


def _apply_attack(
    state: SimState, actor: SimUnit, decision: Decision, params: SimParams
) -> bool:
    """Resolve one engagement in the live game's order (module docstring).

    Returns True when the attacker's strike destroyed the struck unit --
    target or interceptor alike -- which grants re-activation.
    """
    target = state.unit(decision.target_id)
    if target is None or not target.alive:
        return False
    weapon = actor.weapon(decision.weapon)
    if weapon is None or weapon.map_weapon or actor.en < weapon.en_cost:
        return False
    dist = chebyshev(actor.pos, target.pos)
    if not (weapon.range_min <= dist <= weapon.range_max):
        return False

    actor.en -= weapon.en_cost
    response = decision.defense
    struck = target
    mult = _stance_multiplier(response, params)
    interceptor = None
    if response is not None and response.support_defend:
        interceptor = find_support_defender(state, target)
        if interceptor is not None:
            struck = interceptor
            mult = _interception_multiplier(interceptor, params)

    charge_pending = interceptor is not None

    def land(shooter: SimUnit, shot: SimWeapon, landed: bool) -> None:
        nonlocal charge_pending
        if not landed:
            return
        if charge_pending:
            interceptor.support_defend_charges -= 1
            charge_pending = False
        struck.hp -= compute_damage(shooter, struck, shot, mult, params)
        _apply_debuff(state, shot, struck)

    if decision.support:
        volley = find_support_attackers(state, actor, target)
        volley = volley[: max(0, params.max_support_attackers)]
        support_hit = True if decision.support_hit is None else decision.support_hit
        for supporter, support_weapon in volley:
            supporter.support_attack_charges -= 1
            supporter.en -= support_weapon.en_cost
            land(supporter, support_weapon, support_hit)

    hit = True if decision.hit is None else decision.hit
    land(actor, weapon, hit)
    killed = not struck.alive

    if response is not None and target.alive:
        if response.support_attack and actor.alive:
            _apply_support_volley(state, target, actor, decision, params)
        if response.kind == DefenseKind.COUNTER and actor.alive:
            _apply_counter(state, target, actor, decision, params)

    return killed


def _find_attack_shield(state: SimState, attacker: SimUnit) -> SimUnit | None:
    for u in state.units:
        if u is attacker or not u.alive or u.faction is not attacker.faction:
            continue
        if not u.attack_shield or u.support_defend_charges <= 0:
            continue
        if chebyshev(u.pos, attacker.pos) <= u.move_range:
            return u
    return None


def _apply_map_attack(
    state: SimState, actor: SimUnit, decision: Decision, params: SimParams
) -> None:
    weapon = actor.weapon(decision.weapon)
    if weapon is None or not weapon.map_weapon or decision.aim is None:
        return
    if actor.weapon_ammo.get(weapon.name, 0) <= 0 or actor.en < weapon.en_cost:
        return
    dist = chebyshev(actor.pos, decision.aim)
    if not (weapon.range_min <= dist <= weapon.range_max):
        return
    actor.weapon_ammo[weapon.name] -= 1
    actor.en -= weapon.en_cost
    for victim in targets_of(state, actor):
        if chebyshev(victim.pos, decision.aim) <= weapon.blast:
            victim.hp -= compute_damage(
                actor, victim, weapon, formulas.NO_DEFENSE_MULTIPLIER, params
            )
            _apply_debuff(state, weapon, victim)


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
    if not hit:
        return
    struck = attacker
    mult = formulas.NO_DEFENSE_MULTIPLIER
    shield_bearer = _find_attack_shield(state, attacker)
    if shield_bearer is not None:
        shield_bearer.support_defend_charges -= 1
        struck = shield_bearer
        mult = _interception_multiplier(shield_bearer, params)
    struck.hp -= compute_damage(defender, struck, weapon, mult, params)
    _apply_debuff(state, weapon, struck)


def _apply_support_volley(
    state: SimState,
    defender: SimUnit,
    attacker: SimUnit,
    decision: Decision,
    params: SimParams,
) -> None:
    volley = find_support_attackers(state, defender, attacker)
    volley = volley[: max(0, params.max_support_attackers)]
    hit = True if decision.support_hit is None else decision.support_hit
    for supporter, weapon in volley:
        supporter.support_attack_charges -= 1
        supporter.en -= weapon.en_cost
        if hit:
            attacker.hp -= compute_damage(supporter, attacker, weapon, 1.0, params)
            _apply_debuff(state, weapon, attacker)


def _apply_skill(actor: SimUnit, state: SimState, decision: Decision) -> bool:
    """Fire a skill from the actor's inventory; return whether it ends the turn."""
    skill = next(
        (s for s in actor.skills if s.kind == decision.kind and s.uses > 0), None
    )
    if skill is None:
        return True
    skill.uses -= 1
    target = state.unit(decision.target_id) or actor
    amount = decision.amount if decision.amount is not None else skill.amount
    if decision.kind == DecisionKind.SKILL_EN_REFILL:
        gain = int(amount) if amount is not None else target.en_max
        target.en = min(target.en_max, target.en + gain)
    elif decision.kind == DecisionKind.SKILL_HEAL:
        gain = int(amount) if amount is not None else target.max_hp
        target.hp = min(target.max_hp, target.hp + gain)
    return skill.ends_turn


def step(
    state: SimState,
    decision: Decision,
    *,
    move_validator: MoveValidator | None = None,
    params: SimParams = DEFAULT_PARAMS,
    events: EventTable | None = None,
) -> SimState:
    """Apply one decision to a copy of state and return the new state."""
    s = state.clone()
    actor = s.unit(decision.unit_id)
    if actor is None or not actor.alive:
        _advance_until_pending(s, params, events)
        return s

    if decision.move_to is not None and decision.kind != DecisionKind.MAP_ATTACK:
        validate = move_validator or default_move_validator
        if validate(s, actor, decision.move_to):
            actor.pos = decision.move_to

    killed = False
    ends_turn = True
    if decision.kind == DecisionKind.ATTACK:
        killed = _apply_attack(s, actor, decision, params)
    elif decision.kind == DecisionKind.MAP_ATTACK:
        _apply_map_attack(s, actor, decision, params)
    elif decision.kind in (DecisionKind.SKILL_EN_REFILL, DecisionKind.SKILL_HEAL):
        ends_turn = _apply_skill(actor, s, decision)

    if killed and actor.alive and actor.react_charges > 0:
        actor.react_charges -= 1
        actor.acted = False
    else:
        actor.acted = ends_turn

    _remove_dead(s)
    _events_after_step(s, events)
    _advance_until_pending(s, params, events)
    return s
