"""The battle state in Python (spec: docs/spec/battle-engine-protocol.md).

The Go package 'engine/protocol' holds the same structs in 'state.go'. A change
here needs the same change there.

The file holds the data of one battle and the accessors that read it. It holds
no rule: the engine answers every question that needs one.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .contract import ActionKind, Cell, Faction, SkillAffects, SkillSource, Stance


@dataclass(frozen=True)
class Rules:
    """機制倍率與上限；逐項實測狀態見 docs/reference/combat-formulas.md 待標定清單。"""

    defend_multiplier: float = 0.8
    shield_multiplier: float = 0.6
    support_defend_multiplier: float = 0.8
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
    usable_after_move: bool = True
    blast: int = 0
    debuff_kind: str | None = None
    debuff_magnitude: float = 0.0


@dataclass
class Skill:
    """The area fields hold no 'self' value of 'affects'.

    A skill that acts on the caster alone is 'range_min' 0, 'range_max' 0,
    'blast' 0 and 'affects' ally: the area is the cell of the caster, and the
    caster is an ally in its own cell.
    """

    kind: ActionKind
    source: SkillSource = SkillSource.UNIT
    amount: float | None = None
    uses: int = 1
    ends_activation: bool = True
    usable_after_move: bool = True
    range_min: int = 0
    range_max: int = 0
    blast: int = 0
    affects: SkillAffects = SkillAffects.ALLY


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
    # The size is data only. The geometry of this module gives every unit one
    # cell. The engine holds the footprint rule (issue #61).
    size: Cell = (1, 1)
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
class StageEvent:
    """A scripted event.

    The trigger is {"type": "kill", "uid", "within_turn"?} or
    {"type": "turn_start", "turn"}. The effect is {"type": "spawn", "units"} or
    {"type": "weaken", "uids", "attack_multiplier"?, "defense_multiplier"?}.

    An unknown type does nothing and reports nothing, because 'step' runs every event
    at every node. The caller validates the table.
    """

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


@dataclass(frozen=True)
class Reaction:
    """The answer of the defender to one strike.

    A stance of None is a strike that settles no reaction. The contract holds
    no such value, and the field is absent on the wire.
    """

    stance: Stance | None = None
    weapon: str | None = None
    support_defender: str | None = None
    support_attackers: tuple[str, ...] = ()


@dataclass(frozen=True)
class Decision:
    """One action of one unit."""

    unit_id: str
    kind: ActionKind
    move_to: Cell | None = None
    target_id: str | None = None
    weapon: str | None = None
    amount: float | None = None
    reaction: Reaction | None = None
    support_attackers: tuple[str, ...] = ()
    aim: Cell | None = None
    hit: bool | None = None
    counter_hit: bool | None = None
    support_hit: bool | None = None
