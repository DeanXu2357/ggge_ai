"""The battle state in Python (spec: docs/spec/battle-engine-protocol.md).

The Go package 'engine/battle' holds the same structs in 'snapshot.go' and
'decision.go'. A change here needs the same change there.

The file holds the data of one battle and the accessors that read it. It holds
no rule: the engine answers every question that needs one.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .contract import (
    ActionKind,
    Cell,
    Direction,
    Faction,
    MapWeaponAffects,
    SkillAffects,
    SkillSource,
    Stance,
    Terrain,
)


@dataclass(frozen=True)
class ShapeRange:
    """A set of cell offsets from an origin, and the heading that turns them."""

    cells: list[Cell] = field(default_factory=list)
    direction: Direction = Direction.NONE


@dataclass(frozen=True)
class Weapon:
    """A direct weapon: it strikes one unit, and an exchange resolves it."""

    name: str
    power: float
    range_min: int = 1
    range_max: int = 1
    en_cost: int = 0
    accuracy: float = 0.0
    usable_after_move: bool = True
    debuff_kind: str | None = None
    debuff_magnitude: float = 0.0
    categories: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MapWeapon:
    """An area weapon: it strikes every unit of its shape, and it starts no
    exchange. No rule of this version fires one (issue #79).

    apply_shape holds 'map_weapon_shooting_range': the cells where the center
    of the strike can sit. effect_shape holds 'map_weapon_effect_range': the
    cells that the strike hits. An empty apply_shape is no choice of center:
    the weapon opens its area at the cell of the caster.
    """

    name: str
    power: float
    apply_shape: ShapeRange = field(default_factory=ShapeRange)
    effect_shape: ShapeRange = field(default_factory=ShapeRange)
    ammo_max: int = 0
    en_cost: int = 0
    accuracy: float = 0.0
    affects: MapWeaponAffects = MapWeaponAffects.ENEMY
    usable_after_move: bool = True
    debuff_kind: str | None = None
    debuff_magnitude: float = 0.0
    categories: list[str] = field(default_factory=list)


@dataclass
class Skill:
    """A skill that acts on a set of cells.

    apply_shape holds the cells where the center of the skill can sit, and no
    datamine column fills it. effect_shape holds 'effect_range': the cells that
    the skill acts on. An empty apply_shape is no choice of center: the skill
    opens its area at the cell of the caster.
    """

    kind: str
    source: SkillSource = SkillSource.MECH
    amount: float | None = None
    uses: int = 1
    ends_activation: bool = True
    usable_after_move: bool = True
    apply_shape: ShapeRange = field(default_factory=ShapeRange)
    effect_shape: ShapeRange = field(default_factory=ShapeRange)
    affects: SkillAffects = SkillAffects.ALLY


@dataclass(frozen=True)
class Debuff:
    kind: str
    magnitude: float
    applied_phase: int


@dataclass
class Ability:
    """One effect line of a mech or of a pilot.

    The kind names the effect; the other fields hold its number and its
    conditions. A condition the line does not carry is zero, or None for the
    enum conditions. A kind the engine does not model travels as it came.
    """

    kind: str
    percent: float = 0.0
    plus: int = 0
    enemy_tag: int = 0
    mech_tag: int = 0
    pilot_tag: int = 0
    hp_rate_lte: int = 0
    hp_rate_gte: int = 0
    mech_type: int = 0
    strike_role: str | None = None
    weapon_attribute: str | None = None
    weapon_category: str | None = None


@dataclass
class Pilot:
    """The pilot of the pairing. A formula reads it at computation time."""

    ranged: float = 0.0
    melee: float = 0.0
    awaken: float = 0.0
    defense: float = 0.0
    reaction: float = 0.0
    sp: int = 0
    tags: list[int] = field(default_factory=list)
    abilities: list[Ability] = field(default_factory=list)


@dataclass
class Mech:
    """The machine of the pairing. A formula reads it at computation time."""

    hp: int = 0
    en: int = 0
    attack: float = 0.0
    defense: float = 0.0
    mobility: float = 0.0
    move_range: int = 0
    weapons: list[Weapon] = field(default_factory=list)
    map_weapons: list[MapWeapon] = field(default_factory=list)
    tags: list[int] = field(default_factory=list)
    type: int = 0
    abilities: list[Ability] = field(default_factory=list)


@dataclass
class Unit:
    """The current state of one pairing on the board.

    The unit records the values of the moment. The pilot and the mech carry the
    base data and the lines, and the engine derives every maximum from them at
    assembly, so no maximum travels here.

    The unit carries no id: the position of the unit in 'BattleState.units' is
    its id. map_weapon_ammo holds one count for each entry of mech.map_weapons,
    in the same order.
    """

    faction: Faction
    # The size is data only. The geometry of this module gives every unit one
    # cell. The engine holds the footprint rule (issue #61).
    size: Cell = (1, 1)
    # The value column, in the order of the Go 'UnitValues' that the unit
    # payload embeds and the terminal values of 'act' carry.
    pos: Cell = (0, 0)
    hp: int = 1
    en: int = 0
    sp: int = 0
    mp: int = 0
    move_range: int = 0
    acted: bool = False
    chance_steps: int = 0
    support_attack_charges: int = 0
    support_defend_charges: int = 0
    skills: list[Skill] = field(default_factory=list)
    map_weapon_ammo: list[int] = field(default_factory=list)
    debuffs: list[Debuff] = field(default_factory=list)
    pilot: Pilot = field(default_factory=Pilot)
    mech: Mech = field(default_factory=Mech)
    has_shield: bool = False
    support_defend_when_attack: bool = False

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def clone(self) -> Unit:
        return replace(
            self,
            pilot=replace(
                self.pilot,
                tags=list(self.pilot.tags),
                abilities=[replace(a) for a in self.pilot.abilities],
            ),
            mech=replace(
                self.mech,
                weapons=list(self.mech.weapons),
                tags=list(self.mech.tags),
                abilities=[replace(a) for a in self.mech.abilities],
            ),
            skills=[replace(s) for s in self.skills],
            map_weapon_ammo=list(self.map_weapon_ammo),
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


@dataclass(frozen=True)
class TerrainCell:
    cell: Cell
    terrain: Terrain


@dataclass
class BattleState:
    units: list[Unit] = field(default_factory=list)
    phase: Faction = Faction.ALLY
    turn: int = 1
    bounds: tuple[Cell, Cell] | None = None
    pending_events: tuple[str, ...] = ()
    fired_events: tuple[str, ...] = ()
    terrain: Terrain | None = None
    terrain_cells: tuple[TerrainCell, ...] = ()

    def unit(self, unit_id: int | None) -> Unit | None:
        if unit_id is None or not 0 <= unit_id < len(self.units):
            return None
        return self.units[unit_id]

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
class ResponseAttack:
    """The answer of the defender to one strike.

    A stance of None is a strike that settles no response attack. The contract
    holds no such value, and the field is absent on the wire.

    Every id below is a position: a unit id is the position of the unit in
    'BattleState.units', and a weapon id is the position of the weapon in
    'Mech.weapons'.
    """

    stance: Stance | None = None
    weapon_id: int | None = None
    stated: Stated | None = None
    support_attackers: tuple[SupportAttacker, ...] = ()
    support_defender_id: int | None = None


@dataclass(frozen=True)
class Stated:
    """The behaviors of one strike that the caller fixes: the critical of the
    shooter and the hit of the strike."""

    crit: bool = False
    hit: bool = False


@dataclass(frozen=True)
class SupportAttacker:
    """One support attacker of one side, with the weapon it fires."""

    unit_id: int
    weapon_id: int
    stated: Stated | None = None


@dataclass(frozen=True)
class Decision:
    """One action of one unit.

    Exactly one of weapon_id and map_weapon_id is filled on an attack. Every
    other kind of action fills neither.
    """

    unit_id: int
    kind: ActionKind
    move_to: Cell | None = None
    target_id: int | None = None
    weapon_id: int | None = None
    map_weapon_id: int | None = None
    amount: float | None = None
    response_attack: ResponseAttack | None = None
    support_defender_id: int | None = None
    support_attacker_ids: tuple[int, ...] = ()
    aim: Cell | None = None
    hit: bool | None = None
    counter_hit: bool | None = None
    support_hit: bool | None = None
