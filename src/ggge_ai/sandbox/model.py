"""戰局沙盤的世界模型：格盤幾何、狀態轉移、交戰結算順序、傷害與命中公式。

機制事實出自 docs/combat-formulas.md；機體／駕駛／武裝的數值一律由呼叫端
從畫面或快取餵入，本模組不含任何關卡或單位內容。
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import StrEnum

Cell = tuple[int, int]


class Faction(StrEnum):
    ALLY = "ally"
    ENEMY = "enemy"
    THIRD_PARTY = "third_party"


PHASE_ORDER: tuple[Faction, ...] = (Faction.ALLY, Faction.THIRD_PARTY, Faction.ENEMY)


class MoveKind(StrEnum):
    ATTACK = "attack"
    MAP_ATTACK = "map_attack"
    REPOSITION = "reposition"
    STANDBY = "standby"
    SKILL_EN_REFILL = "skill_en_refill"
    SKILL_HEAL = "skill_heal"


SKILL_KINDS: tuple[MoveKind, ...] = (MoveKind.SKILL_EN_REFILL, MoveKind.SKILL_HEAL)


class Stance(StrEnum):
    NONE = "none"
    DODGE = "dodge"
    DEFEND = "defend"
    SHIELD = "shield"
    COUNTER = "counter"


STANCES: tuple[Stance, ...] = tuple(Stance)

NO_DEFENSE_MULTIPLIER = 1.0
DEFEND_MULTIPLIER = 0.8
SHIELD_MULTIPLIER = 0.6

CRIT_NORMAL = 1.1
CRIT_HIGH_MORALE = 1.2
CRIT_SUPER = 1.3

HIT_BASE = 96.45
HIT_ATK_MOBILITY_COEF = 0.00732
HIT_DEF_MOBILITY_COEF = 0.00662
HIT_PILOT_DIVISOR = 25.0


def _pilot_ratio(pl_atk: float, pl_def: float) -> float:
    return max(0.0, (pl_atk - pl_def) / 5000)


def _unit_ratio(un_atk: float, un_def: float) -> float:
    return max(0.0, (un_atk / 10 - un_def / 10) / 5000)


def _pilot_sigmoid(pl_atk: float, pl_def: float) -> float:
    return 1.0 / (math.exp(250 * (pl_def - pl_atk) / 100000) + 1.0)


def _unit_sigmoid(un_atk: float, un_def: float) -> float:
    return 1.0 / (math.exp(25 * (un_def - un_atk) / 100000) + 1.0)


def _attack_correction(un_atk: float, pl_atk: float) -> float:
    return 100.0 / (math.exp((5000 - (un_atk + pl_atk * 2) / 10) * 30 / 100000) + 1.0)


def _defense_correction(un_def: float, pl_def: float) -> float:
    return -40.0 / (math.exp((5000 - (un_def + pl_def * 2) / 10) * 3 / 100000) + 1.0)


def base_damage(power: float, pl_atk: float, pl_def: float, un_atk: float, un_def: float) -> float:
    return power * (
        _pilot_ratio(pl_atk, pl_def)
        + _unit_ratio(un_atk, un_def)
        + _pilot_sigmoid(pl_atk, pl_def)
        + _unit_sigmoid(un_atk, un_def)
    )


def combat_base_damage(
    power: float,
    pl_atk: float,
    pl_def: float,
    un_atk: float,
    un_def: float,
    *,
    terrain: float = 1.0,
) -> float:
    factor = 1.0 + _attack_correction(un_atk, pl_atk) + _defense_correction(un_def, pl_def)
    return base_damage(power, pl_atk, pl_def, un_atk, un_def) * factor / terrain


def damage_scale(bonuses: float = 0.0, penalties: float = 0.0) -> float:
    return 1.0 + bonuses - penalties


def final_damage(
    combat_base: float,
    *,
    scale: float = 1.0,
    defense_multiplier: float = NO_DEFENSE_MULTIPLIER,
) -> float:
    return combat_base * scale * defense_multiplier


def critical_damage(
    combat_base: float,
    *,
    scale: float = 1.0,
    defense_multiplier: float = NO_DEFENSE_MULTIPLIER,
    critical: float = CRIT_NORMAL,
) -> float:
    return combat_base * scale * defense_multiplier * critical


def expected_damage(
    power: float,
    pl_atk: float,
    pl_def: float,
    un_atk: float,
    un_def: float,
    *,
    terrain: float = 1.0,
    bonuses: float = 0.0,
    penalties: float = 0.0,
    defense_multiplier: float = NO_DEFENSE_MULTIPLIER,
) -> float:
    return final_damage(
        combat_base_damage(power, pl_atk, pl_def, un_atk, un_def, terrain=terrain),
        scale=damage_scale(bonuses, penalties),
        defense_multiplier=defense_multiplier,
    )


def hit_rate_percent(
    atk_mobility: float,
    def_mobility: float,
    pl_atk: float,
    def_reaction: float,
    *,
    ability_correction: float = 0.0,
    base: float = HIT_BASE,
    clamp: bool = True,
) -> float:
    rate = (
        base
        + HIT_ATK_MOBILITY_COEF * atk_mobility
        - HIT_DEF_MOBILITY_COEF * def_mobility
        + (pl_atk - def_reaction) / HIT_PILOT_DIVISOR
        + ability_correction
    )
    return max(0.0, min(100.0, rate)) if clamp else rate


def hit_probability(
    atk_mobility: float,
    def_mobility: float,
    pl_atk: float,
    def_reaction: float,
    *,
    ability_correction: float = 0.0,
    base: float = HIT_BASE,
) -> float:
    return (
        hit_rate_percent(
            atk_mobility,
            def_mobility,
            pl_atk,
            def_reaction,
            ability_correction=ability_correction,
            base=base,
        )
        / 100.0
    )


@dataclass(frozen=True)
class Rules:
    """機制倍率與上限；逐項實測狀態見 docs/combat-formulas.md 待標定清單。"""

    defend_multiplier: float = DEFEND_MULTIPLIER
    shield_multiplier: float = SHIELD_MULTIPLIER
    support_defend_multiplier: float = DEFEND_MULTIPLIER
    dodge_hit_penalty: float = 20.0
    terrain: float = 1.0
    max_support_attackers: int = 3
    en_regen_fraction: float = 0.10


DEFAULT_RULES = Rules()


@dataclass(frozen=True)
class Weapon:
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
class Skill:
    kind: MoveKind
    amount: float | None = None
    uses: int = 1
    ends_activation: bool = True


@dataclass(frozen=True)
class Debuff:
    kind: str
    magnitude: float
    applied_phase: int


@dataclass
class Unit:
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
    weapons: list[Weapon] = field(default_factory=list)
    skills: list[Skill] = field(default_factory=list)
    acted: bool = False
    chance_steps: int = 0
    chance_steps_max: int = 0
    support_defend_charges: int = 0
    support_defend_charges_max: int = 0
    support_attack_charges: int = 0
    support_attack_charges_max: int = 0
    has_shield: bool = False
    attack_shield: bool = False
    interception_reduction: float = 0.0
    ammo: dict[str, int] = field(default_factory=dict)
    debuffs: list[Debuff] = field(default_factory=list)

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def weapon(self, name: str | None) -> Weapon | None:
        if name is None:
            return self.weapons[0] if self.weapons else None
        for w in self.weapons:
            if w.name == name:
                return w
        return None

    def clone(self) -> Unit:
        return replace(
            self,
            weapons=list(self.weapons),
            skills=[replace(s) for s in self.skills],
            ammo=dict(self.ammo),
            debuffs=list(self.debuffs),
        )


@dataclass(frozen=True)
class Reaction:
    """防守方對一次來襲的反應：姿態、支援防禦攔截、支援反擊。"""

    stance: Stance = Stance.NONE
    weapon: str | None = None
    support_defend: bool = False
    support_attack: bool = True


@dataclass(frozen=True)
class Decision:
    """一個單位的一次行動；hit/counter_hit/support_hit 是命中節點的擲骰結果。"""

    unit_id: str
    kind: MoveKind
    move_to: Cell | None = None
    target_id: str | None = None
    weapon: str | None = None
    amount: float | None = None
    reaction: Reaction | None = None
    support: bool = True
    aim: Cell | None = None
    hit: bool | None = None
    counter_hit: bool | None = None
    support_hit: bool | None = None


@dataclass(frozen=True)
class StageEvent:
    """劇本事件。trigger：{"type": "kill", "uid", "within_turn"?} 或
    {"type": "turn_start", "turn"}；effect：{"type": "spawn", "units"} 或
    {"type": "weaken", "uids", "attack_multiplier"?, "defense_multiplier"?}。
    未知型別靜默無操作——step 每個節點都會跑，驗證屬呼叫端。"""

    event_id: str
    trigger: dict
    effect: dict


EventTable = dict[str, StageEvent]


@dataclass
class BattleState:
    units: list[Unit] = field(default_factory=list)
    phase: Faction = Faction.ALLY
    turn: int = 1
    bounds: tuple[Cell, Cell] | None = None
    pending_events: tuple[str, ...] = ()
    fired_events: tuple[str, ...] = ()

    def unit(self, unit_id: str | None) -> Unit | None:
        if unit_id is None:
            return None
        for u in self.units:
            if u.unit_id == unit_id:
                return u
        return None

    def by_faction(self, faction: Faction) -> list[Unit]:
        return [u for u in self.units if u.faction is faction and u.alive]

    def allies(self) -> list[Unit]:
        return self.by_faction(Faction.ALLY)

    def enemies(self) -> list[Unit]:
        return self.by_faction(Faction.ENEMY)

    def clone(self) -> BattleState:
        return BattleState(
            units=[u.clone() for u in self.units],
            phase=self.phase,
            turn=self.turn,
            bounds=self.bounds,
            pending_events=self.pending_events,
            fired_events=self.fired_events,
        )

    def phase_index(self) -> int:
        return self.turn * len(PHASE_ORDER) + PHASE_ORDER.index(self.phase)

    def key(self) -> tuple:
        # pending 與 fired 都要進 key：帶時限的 kill 事件會「過期」，只看 pending
        # 分不出已觸發與已過期，而已觸發的 weaken 改了 key 不收的靜態值。
        units = tuple(
            sorted(
                (
                    u.unit_id,
                    str(u.faction),
                    u.pos,
                    u.hp,
                    u.en,
                    u.acted,
                    u.chance_steps,
                    u.support_defend_charges,
                    u.support_attack_charges,
                    tuple(sorted(u.ammo.items())),
                    tuple(sorted((d.kind, d.magnitude, d.applied_phase) for d in u.debuffs)),
                    tuple(s.uses for s in u.skills),
                )
                for u in self.units
            )
        )
        return (str(self.phase), self.turn, self.pending_events, self.fired_events, units)


ReachFn = Callable[[BattleState, Unit], set[Cell]]

_KING_STEPS: tuple[Cell, ...] = (
    (-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1),
)


def chebyshev(a: Cell, b: Cell) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def in_band(distance: int, weapon: Weapon) -> bool:
    return weapon.range_min <= distance <= weapon.range_max


def blocking_cells(state: BattleState, unit: Unit) -> set[Cell]:
    return {
        u.pos for u in state.units if u.alive and u is not unit and u.faction is not unit.faction
    }


def occupied_cells(state: BattleState, unit: Unit) -> set[Cell]:
    return {u.pos for u in state.units if u.alive and u is not unit}


def _in_bounds(state: BattleState, cell: Cell) -> bool:
    if state.bounds is None:
        return True
    (min_x, min_y), (max_x, max_y) = state.bounds
    return min_x <= cell[0] <= max_x and min_y <= cell[1] <= max_y


def reachable_cells(state: BattleState, unit: Unit) -> set[Cell]:
    blocked = blocking_cells(state, unit)
    occupied = occupied_cells(state, unit)
    seen = {unit.pos}
    out = {unit.pos}
    frontier = deque([(unit.pos, 0)])
    while frontier:
        pos, dist = frontier.popleft()
        if dist == unit.move_range:
            continue
        for dx, dy in _KING_STEPS:
            nxt = (pos[0] + dx, pos[1] + dy)
            if nxt in seen or nxt in blocked or not _in_bounds(state, nxt):
                continue
            seen.add(nxt)
            frontier.append((nxt, dist + 1))
            if nxt not in occupied:
                out.add(nxt)
    return out


def nearest_free_cell(cell: Cell, taken: set[Cell]) -> Cell:
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


def reach_of(state: BattleState, unit: Unit, reach_fn: ReachFn | None = None) -> set[Cell]:
    return (reach_fn or reachable_cells)(state, unit)


def opposing_faction(faction: Faction) -> Faction:
    return Faction.ENEMY if faction is Faction.ALLY else Faction.ALLY


def targets_of(state: BattleState, unit: Unit) -> list[Unit]:
    return state.by_faction(opposing_faction(unit.faction))


def find_support_defender(state: BattleState, defender: Unit) -> Unit | None:
    for u in state.units:
        if u is defender or not u.alive or u.faction is not defender.faction:
            continue
        if u.support_defend_charges <= 0:
            continue
        if chebyshev(u.pos, defender.pos) <= u.move_range:
            return u
    return None


def find_attack_shield(state: BattleState, attacker: Unit) -> Unit | None:
    for u in state.units:
        if u is attacker or not u.alive or u.faction is not attacker.faction:
            continue
        if not u.attack_shield or u.support_defend_charges <= 0:
            continue
        if chebyshev(u.pos, attacker.pos) <= u.move_range:
            return u
    return None


def find_support_attackers(
    state: BattleState, supported: Unit, foe: Unit
) -> list[tuple[Unit, Weapon]]:
    out: list[tuple[Unit, Weapon]] = []
    for u in state.units:
        if u is supported or not u.alive or u.faction is not supported.faction:
            continue
        if u.support_attack_charges <= 0:
            continue
        if chebyshev(u.pos, supported.pos) > u.move_range:
            continue
        dist = chebyshev(u.pos, foe.pos)
        for w in u.weapons:
            if not w.map_weapon and u.en >= w.en_cost and in_band(dist, w):
                out.append((u, w))
                break
    return out


def _proximity(cell: Cell, anchor: Cell) -> tuple[int, int, Cell]:
    dx, dy = cell[0] - anchor[0], cell[1] - anchor[1]
    return (chebyshev(cell, anchor), dx * dx + dy * dy, cell)


def standby(unit_id: str) -> Decision:
    return Decision(unit_id=unit_id, kind=MoveKind.STANDBY)


def legal_attacks(
    state: BattleState, unit: Unit, *, reach: set[Cell] | None = None
) -> list[Decision]:
    cells = reachable_cells(state, unit) if reach is None else reach
    out: list[Decision] = []
    for target in targets_of(state, unit):
        for weapon in unit.weapons:
            if weapon.map_weapon or unit.en < weapon.en_cost:
                continue
            band = [c for c in cells if in_band(chebyshev(c, target.pos), weapon)]
            if not band:
                continue
            dest = min(band, key=lambda c: _proximity(c, unit.pos))
            out.append(
                Decision(
                    unit_id=unit.unit_id,
                    kind=MoveKind.ATTACK,
                    move_to=None if dest == unit.pos else dest,
                    target_id=target.unit_id,
                    weapon=weapon.name,
                )
            )
    return out


def legal_map_attacks(state: BattleState, unit: Unit) -> list[Decision]:
    out: list[Decision] = []
    for weapon in unit.weapons:
        if not weapon.map_weapon:
            continue
        if unit.ammo.get(weapon.name, 0) <= 0 or unit.en < weapon.en_cost:
            continue
        for target in targets_of(state, unit):
            if in_band(chebyshev(unit.pos, target.pos), weapon):
                out.append(
                    Decision(
                        unit_id=unit.unit_id,
                        kind=MoveKind.MAP_ATTACK,
                        weapon=weapon.name,
                        aim=target.pos,
                    )
                )
    return out


def legal_skills(unit: Unit) -> list[Decision]:
    out: list[Decision] = []
    for skill in unit.skills:
        if skill.uses <= 0:
            continue
        if skill.kind is MoveKind.SKILL_EN_REFILL and unit.en < unit.en_max:
            out.append(Decision(unit_id=unit.unit_id, kind=skill.kind, amount=skill.amount))
        elif skill.kind is MoveKind.SKILL_HEAL and unit.hp < unit.max_hp:
            out.append(Decision(unit_id=unit.unit_id, kind=skill.kind, amount=skill.amount))
    return out


def reposition_moves(
    state: BattleState, unit: Unit, *, reach: set[Cell] | None = None
) -> list[Decision]:
    if unit.move_range <= 0:
        return []
    targets = targets_of(state, unit)
    if not targets:
        return []
    cells = reachable_cells(state, unit) if reach is None else reach
    picks = [min(cells, key=lambda c: _proximity(c, t.pos)) for t in targets]
    nearest = min(targets, key=lambda t: chebyshev(unit.pos, t.pos))
    picks.append(max(cells, key=lambda c: _proximity(c, nearest.pos)))
    out: list[Decision] = []
    seen: set[Cell] = set()
    for cell in picks:
        if cell == unit.pos or cell in seen:
            continue
        seen.add(cell)
        out.append(Decision(unit_id=unit.unit_id, kind=MoveKind.REPOSITION, move_to=cell))
    return out


def strike_damage(
    attacker: Unit,
    defender: Unit,
    weapon: Weapon,
    *,
    defense_multiplier: float = NO_DEFENSE_MULTIPLIER,
    rules: Rules = DEFAULT_RULES,
) -> int:
    return int(
        round(
            expected_damage(
                weapon.power,
                attacker.pilot_attack,
                defender.pilot_defense,
                attacker.unit_attack,
                defender.unit_defense,
                terrain=rules.terrain,
                bonuses=sum(d.magnitude for d in defender.debuffs),
                defense_multiplier=defense_multiplier,
            )
        )
    )


def strike_hit_probability(
    attacker: Unit,
    defender: Unit,
    weapon: Weapon | None,
    *,
    dodging: bool = False,
    rules: Rules = DEFAULT_RULES,
) -> float:
    ability = weapon.accuracy if weapon is not None else 0.0
    if dodging:
        ability -= rules.dodge_hit_penalty
    return hit_probability(
        attacker.mobility,
        defender.mobility,
        attacker.pilot_attack,
        defender.reaction,
        ability_correction=ability,
    )


def decision_hit_probability(
    state: BattleState, decision: Decision, rules: Rules = DEFAULT_RULES
) -> float:
    actor = state.unit(decision.unit_id)
    target = state.unit(decision.target_id)
    if actor is None or target is None:
        return 1.0
    dodging = decision.reaction is not None and decision.reaction.stance is Stance.DODGE
    return strike_hit_probability(
        actor, target, actor.weapon(decision.weapon), dodging=dodging, rules=rules
    )


def _stance_multiplier(reaction: Reaction | None, rules: Rules) -> float:
    if reaction is None:
        return NO_DEFENSE_MULTIPLIER
    if reaction.stance is Stance.DEFEND:
        return rules.defend_multiplier
    if reaction.stance is Stance.SHIELD:
        return rules.shield_multiplier
    return NO_DEFENSE_MULTIPLIER


def _interception_multiplier(interceptor: Unit, rules: Rules) -> float:
    base = rules.shield_multiplier if interceptor.has_shield else rules.support_defend_multiplier
    return base * (1.0 - interceptor.interception_reduction)


def _counter_weapon(defender: Unit, name: str | None, attacker: Unit) -> Weapon | None:
    dist = chebyshev(defender.pos, attacker.pos)
    pool = defender.weapons if name is None else [w for w in defender.weapons if w.name == name]
    for w in pool:
        if w.map_weapon or not w.can_counter or defender.en < w.en_cost:
            continue
        if in_band(dist, w):
            return w
    return None


def _apply_debuff(state: BattleState, weapon: Weapon, victim: Unit) -> None:
    if weapon.debuff_kind is None:
        return
    existing = next((d for d in victim.debuffs if d.kind == weapon.debuff_kind), None)
    if existing is not None:
        if existing.magnitude >= weapon.debuff_magnitude:
            return
        victim.debuffs.remove(existing)
    victim.debuffs.append(Debuff(weapon.debuff_kind, weapon.debuff_magnitude, state.phase_index()))


def _expire_debuffs(state: BattleState) -> None:
    now = state.phase_index()
    for u in state.units:
        if u.debuffs:
            u.debuffs = [d for d in u.debuffs if now - d.applied_phase < len(PHASE_ORDER)]


def _begin_phase(state: BattleState, faction: Faction, rules: Rules) -> None:
    for u in state.units:
        if u.faction is faction:
            u.acted = False
            u.chance_steps = u.chance_steps_max
            u.support_defend_charges = u.support_defend_charges_max
            u.support_attack_charges = u.support_attack_charges_max
            u.en = min(u.en_max, u.en + int(round(u.en_max * rules.en_regen_fraction)))


def _pending(state: BattleState, faction: Faction) -> list[Unit]:
    return [u for u in state.units if u.faction is faction and u.alive and not u.acted]


def _rotate_one(state: BattleState, rules: Rules, events: EventTable | None) -> None:
    idx = PHASE_ORDER.index(state.phase)
    nxt = PHASE_ORDER[(idx + 1) % len(PHASE_ORDER)]
    if nxt is Faction.ALLY:
        state.turn += 1
        _events_on_new_turn(state, events)
    state.phase = nxt
    _expire_debuffs(state)
    _begin_phase(state, nxt, rules)


def _advance_until_pending(state: BattleState, rules: Rules, events: EventTable | None) -> None:
    guard = 0
    while not _pending(state, state.phase) and guard <= len(PHASE_ORDER):
        _rotate_one(state, rules, events)
        guard += 1


def _apply_event_effect(state: BattleState, event: StageEvent) -> None:
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


def _fire_event(state: BattleState, event: StageEvent) -> None:
    _apply_event_effect(state, event)
    state.pending_events = tuple(e for e in state.pending_events if e != event.event_id)
    state.fired_events = (*state.fired_events, event.event_id)


def _events_after_step(state: BattleState, events: EventTable | None) -> None:
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


def _events_on_new_turn(state: BattleState, events: EventTable | None) -> None:
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
                state.pending_events = tuple(e for e in state.pending_events if e != event_id)


def _apply_attack(state: BattleState, actor: Unit, decision: Decision, rules: Rules) -> bool:
    target = state.unit(decision.target_id)
    if target is None or not target.alive:
        return False
    weapon = actor.weapon(decision.weapon)
    if weapon is None or weapon.map_weapon or actor.en < weapon.en_cost:
        return False
    if not in_band(chebyshev(actor.pos, target.pos), weapon):
        return False

    actor.en -= weapon.en_cost
    reaction = decision.reaction
    struck = target
    multiplier = _stance_multiplier(reaction, rules)
    interceptor = None
    if reaction is not None and reaction.support_defend:
        interceptor = find_support_defender(state, target)
        if interceptor is not None:
            struck = interceptor
            multiplier = _interception_multiplier(interceptor, rules)

    charge_pending = interceptor is not None

    def land(shooter: Unit, shot: Weapon, landed: bool) -> None:
        nonlocal charge_pending
        if not landed:
            return
        if charge_pending:
            interceptor.support_defend_charges -= 1
            charge_pending = False
        struck.hp -= strike_damage(
            shooter, struck, shot, defense_multiplier=multiplier, rules=rules
        )
        _apply_debuff(state, shot, struck)

    if decision.support:
        volley = find_support_attackers(state, actor, target)
        support_hit = True if decision.support_hit is None else decision.support_hit
        for supporter, support_weapon in volley[: max(0, rules.max_support_attackers)]:
            supporter.support_attack_charges -= 1
            supporter.en -= support_weapon.en_cost
            land(supporter, support_weapon, support_hit)

    land(actor, weapon, True if decision.hit is None else decision.hit)
    killed = not struck.alive

    # reaction is None ＝ 這一擊沒有防守方反應要結算（樹在別處決定），不是「放棄反擊」。
    if reaction is not None and target.alive:
        if reaction.support_attack and actor.alive:
            _apply_support_volley(state, target, actor, decision, rules)
        if reaction.stance is Stance.COUNTER and actor.alive:
            _apply_counter(state, target, actor, decision, rules)

    return killed


def _apply_support_volley(
    state: BattleState, defender: Unit, attacker: Unit, decision: Decision, rules: Rules
) -> None:
    volley = find_support_attackers(state, defender, attacker)
    hit = True if decision.support_hit is None else decision.support_hit
    for supporter, weapon in volley[: max(0, rules.max_support_attackers)]:
        supporter.support_attack_charges -= 1
        supporter.en -= weapon.en_cost
        if hit:
            attacker.hp -= strike_damage(supporter, attacker, weapon, rules=rules)
            _apply_debuff(state, weapon, attacker)


def _apply_counter(
    state: BattleState, defender: Unit, attacker: Unit, decision: Decision, rules: Rules
) -> None:
    name = decision.reaction.weapon if decision.reaction is not None else None
    weapon = _counter_weapon(defender, name, attacker)
    if weapon is None:
        return
    defender.en -= weapon.en_cost
    if decision.counter_hit is False:
        return
    struck = attacker
    multiplier = NO_DEFENSE_MULTIPLIER
    shield_bearer = find_attack_shield(state, attacker)
    if shield_bearer is not None:
        shield_bearer.support_defend_charges -= 1
        struck = shield_bearer
        multiplier = _interception_multiplier(shield_bearer, rules)
    struck.hp -= strike_damage(defender, struck, weapon, defense_multiplier=multiplier, rules=rules)
    _apply_debuff(state, weapon, struck)


def _apply_map_attack(
    state: BattleState, actor: Unit, decision: Decision, rules: Rules
) -> None:
    weapon = actor.weapon(decision.weapon)
    if weapon is None or not weapon.map_weapon or decision.aim is None:
        return
    if actor.ammo.get(weapon.name, 0) <= 0 or actor.en < weapon.en_cost:
        return
    if not in_band(chebyshev(actor.pos, decision.aim), weapon):
        return
    actor.ammo[weapon.name] -= 1
    actor.en -= weapon.en_cost
    for victim in targets_of(state, actor):
        if chebyshev(victim.pos, decision.aim) <= weapon.blast:
            victim.hp -= strike_damage(actor, victim, weapon, rules=rules)
            _apply_debuff(state, weapon, victim)


def _apply_skill(state: BattleState, actor: Unit, decision: Decision) -> bool:
    skill = next((s for s in actor.skills if s.kind is decision.kind and s.uses > 0), None)
    if skill is None:
        return True
    skill.uses -= 1
    target = state.unit(decision.target_id) or actor
    amount = decision.amount if decision.amount is not None else skill.amount
    if decision.kind is MoveKind.SKILL_EN_REFILL:
        gain = int(amount) if amount is not None else target.en_max
        target.en = min(target.en_max, target.en + gain)
    elif decision.kind is MoveKind.SKILL_HEAL:
        gain = int(amount) if amount is not None else target.max_hp
        target.hp = min(target.max_hp, target.hp + gain)
    return skill.ends_activation


def step(
    state: BattleState,
    decision: Decision,
    *,
    rules: Rules = DEFAULT_RULES,
    events: EventTable | None = None,
    reach_fn: ReachFn | None = None,
) -> BattleState:
    s = state.clone()
    actor = s.unit(decision.unit_id)
    if actor is None or not actor.alive:
        _advance_until_pending(s, rules, events)
        return s

    # 地圖炮是移動前限定武裝：施放的那次行動裡永遠不含移動。
    if decision.move_to is not None and decision.kind is not MoveKind.MAP_ATTACK:
        if decision.move_to in reach_of(s, actor, reach_fn):
            actor.pos = decision.move_to

    killed = False
    ends_activation = True
    if decision.kind is MoveKind.ATTACK:
        killed = _apply_attack(s, actor, decision, rules)
    elif decision.kind is MoveKind.MAP_ATTACK:
        _apply_map_attack(s, actor, decision, rules)
    elif decision.kind in SKILL_KINDS:
        ends_activation = _apply_skill(s, actor, decision)

    if killed and actor.alive and actor.chance_steps > 0:
        actor.chance_steps -= 1
        actor.acted = False
    else:
        actor.acted = ends_activation

    s.units = [u for u in s.units if u.alive]
    _events_after_step(s, events)
    _advance_until_pending(s, rules, events)
    return s
