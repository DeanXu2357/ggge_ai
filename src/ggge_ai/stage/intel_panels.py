"""Assemble a UnitIntel from what the panel readers actually read.

The readers report per-field absence; this layer decides what that absence
means for the record and says so out loud. Two rules run through it:

- a field the panel did not yield stays at the UnitIntel default and is named
  in `gaps`, so a caller can tell "read as zero" from "not read";
- a stat the panel showed as an ability delta is not a stat, so it is refused
  and named in `gaps` too.

`pilot_attack` is deliberately left unset. The game splits the pilot's offence
into 射擊值 and 格鬥值 (plus 覺醒值) while sandbox Unit carries one
pilot_attack, and docs/decisions.md settles that the choice belongs to the
layer that knows which weapon is being priced. Callers pass pick= when they
know, or read PanelIntel.pilot_offence and choose per weapon.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..runtime import panels
from ..runtime.panel_text import (
    ATTACK_SHIELD,
    INTERCEPTION_REDUCTION,
    SHIELD_DEFENSE,
    SKILL_KINDS,
    SUPPORT_DEFEND_CHARGE,
    AbilityTexts,
    WeaponText,
)
from ..sandbox.model import MoveKind
from .intel import SkillIntel, UnitIntel, WeaponIntel

SHOOTING_PICK = "shooting"
MELEE_PICK = "melee"
AWAKENING_PICK = "awakening"
PICKS = (SHOOTING_PICK, MELEE_PICK, AWAKENING_PICK)


@dataclass(frozen=True)
class PilotOffence:
    """The three offence values the panel prints, none of them collapsed."""

    shooting: int | None = None
    melee: int | None = None
    awakening: int | None = None

    def pick(self, name: str) -> int | None:
        return getattr(self, name, None)


@dataclass(frozen=True)
class Dynamics:
    """Read off the panel yet barred from UnitIntel: battlefield state that the
    cache must never carry (docs/intel-data-spec.md). Handed back so the caller
    can inject it through Intelligence.unit(hp=, en=) instead of losing it."""

    faction: str | None = None
    mp_current: int | None = None
    mp_max: int | None = None


@dataclass(frozen=True)
class PanelIntel:
    record: UnitIntel
    pilot_offence: PilotOffence = PilotOffence()
    dynamics: Dynamics = Dynamics()
    gaps: tuple[str, ...] = ()
    unsupported: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return not self.gaps


@dataclass
class _Build:
    gaps: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)

    def need(self, name: str, value: int | None, fallback: int) -> int:
        if value is None:
            self.gaps.append(name)
            return fallback
        return value


def _stat(build: _Build, name: str, slot, fallback: int) -> int:
    if slot.delta:
        build.gaps.append(f"{name}:delta")
        return fallback
    return build.need(name, slot.value, fallback)


def weapon_intel(row: panels.WeaponRowRead, text: WeaponText | None, build: _Build) -> WeaponIntel:
    """One weapon card as a WeaponIntel.

    accuracy carries the panel's 命中 as its offset from 100%, which is the
    additive shape sandbox hit_rate_percent expects of ability_correction; the
    reconciliation against a live forecast is batch 2d's job.
    """
    name = text.name if text and text.name else f"weapon_{row.index}"
    if text is None:
        build.gaps.append(f"weapon{row.index}:name")
    if text is not None:
        build.unsupported.extend(text.unsupported)
    if row.power is None:
        build.gaps.append(f"weapon{row.index}:power")
    if row.hit_pct is None:
        build.gaps.append(f"weapon{row.index}:accuracy")
    if row.map_weapon:
        build.gaps.append(f"weapon{row.index}:map_blast")
    elif row.range_min is None or row.range_max is None:
        build.gaps.append(f"weapon{row.index}:range")
    if not row.categories:
        build.gaps.append(f"weapon{row.index}:categories")
    return WeaponIntel(
        name=name,
        power=float(row.power or 0),
        range_min=row.range_min or 1,
        range_max=row.range_max or 1,
        en_cost=row.en_cost or 0,
        accuracy=float(row.hit_pct - 100) if row.hit_pct is not None else 0.0,
        map_weapon=row.map_weapon,
        ammo=row.ammo or 0,
        debuff_kind=text.effect if text else None,
        debuff_magnitude=text.magnitude if text else 0.0,
        categories=row.categories,
        crit_pct=row.crit_pct or 0,
        level=row.level or 0,
    )


def _abilities(texts: AbilityTexts | None, build: _Build) -> dict:
    flags = {
        "has_shield": False,
        "attack_shield": False,
        "interception_reduction": 0.0,
        "support_defend_charges_max": 0,
        "skills": (),
    }
    if texts is None:
        build.gaps.append("abilities")
        return flags
    build.unsupported.extend(texts.unsupported)
    skills: list[SkillIntel] = []
    for entry in texts.entries:
        if entry.effect in SKILL_KINDS:
            skills.append(SkillIntel(kind=MoveKind(entry.effect), amount=entry.magnitude or None))
        elif entry.effect == SHIELD_DEFENSE:
            flags["has_shield"] = True
        elif entry.effect == ATTACK_SHIELD:
            flags["attack_shield"] = True
        elif entry.effect == INTERCEPTION_REDUCTION:
            flags["interception_reduction"] = entry.magnitude
        elif entry.effect == SUPPORT_DEFEND_CHARGE:
            flags["support_defend_charges_max"] += max(1, int(entry.magnitude or 1))
    flags["skills"] = tuple(skills)
    return flags


def unit_intel_from_panels(
    unit_id: str,
    *,
    column: panels.StatColumn | None = None,
    basic: panels.BasicView | None = None,
    weapons: tuple[tuple[panels.WeaponRowRead, WeaponText | None], ...] = (),
    abilities: AbilityTexts | None = None,
    pick: str | None = None,
) -> PanelIntel:
    """Fold every panel read for one unit into a single record."""
    build = _Build()
    offence = PilotOffence()

    max_hp = en_max = move_range = 0
    unit_attack = unit_defense = mobility = 0
    pilot_defense = reaction = pilot_sp = 0
    if column is not None:
        max_hp = _stat(build, "max_hp", column.max_hp, 0)
        en_max = _stat(build, "en_max", column.en_max, 0)
        move_range = _stat(build, "move_range", column.move_range, 0)
        unit_attack = _stat(build, "unit_attack", column.unit_attack, 0)
        unit_defense = _stat(build, "unit_defense", column.unit_defense, 0)
        mobility = _stat(build, "mobility", column.mobility, 0)
        if column.kind in panels.STAGE_KINDS:
            pilot_defense = _stat(build, "pilot_defense", column.pilot_defense, 0)
            reaction = _stat(build, "pilot_reaction", column.pilot_reaction, 0)
            pilot_sp = _stat(build, "pilot_sp", column.pilot_sp, 0)
            offence = PilotOffence(
                shooting=column.pilot_shooting.absolute,
                melee=column.pilot_melee.absolute,
                awakening=column.pilot_awakening.absolute,
            )
    else:
        build.gaps.append("stat_column")

    unit_lv = pilot_lv = 0
    dynamics = Dynamics()
    if basic is not None:
        max_hp = max_hp or build.need("max_hp", basic.max_hp, 0)
        en_max = en_max or build.need("en_max", basic.en_max, 0)
        move_range = move_range or build.need("move_range", basic.move_range, 0)
        unit_lv = build.need("unit_lv", basic.unit_lv, 0)
        pilot_lv = build.need("pilot_lv", basic.pilot_lv, 0)
        pilot_sp = pilot_sp or build.need("pilot_sp", basic.pilot_sp, 0)
        dynamics = Dynamics(
            faction=basic.faction, mp_current=basic.mp_current, mp_max=basic.mp_max
        )

    pilot_attack = 0
    if pick is not None:
        if pick not in PICKS:
            raise ValueError(f"pick must be one of {PICKS}")
        pilot_attack = build.need(f"pilot_{pick}", offence.pick(pick), 0)
    else:
        build.gaps.append("pilot_attack:unpicked")

    weapon_records = tuple(weapon_intel(row, text, build) for row, text in weapons)
    if not weapon_records:
        build.gaps.append("weapons")
    flags = _abilities(abilities, build)

    chance_steps = 0
    if basic is not None and basic.chance_step_badges is not None:
        chance_steps = basic.chance_step_badges
    else:
        build.gaps.append("chance_steps_max")

    record = UnitIntel(
        unit_id=unit_id,
        max_hp=max_hp or 1,
        en_max=en_max,
        unit_attack=float(unit_attack),
        unit_defense=float(unit_defense),
        pilot_attack=float(pilot_attack),
        pilot_defense=float(pilot_defense),
        reaction=float(reaction),
        mobility=float(mobility),
        move_range=move_range,
        weapons=weapon_records,
        skills=flags["skills"],
        chance_steps_max=chance_steps,
        support_defend_charges_max=flags["support_defend_charges_max"],
        has_shield=flags["has_shield"],
        attack_shield=flags["attack_shield"],
        interception_reduction=flags["interception_reduction"],
        pilot_shooting=float(offence.shooting or 0),
        pilot_melee=float(offence.melee or 0),
        pilot_awakening=float(offence.awakening or 0),
        unit_lv=unit_lv,
        pilot_lv=pilot_lv,
        pilot_sp=pilot_sp,
    )
    return PanelIntel(
        record=record,
        pilot_offence=offence,
        dynamics=dynamics,
        gaps=tuple(dict.fromkeys(build.gaps)),
        unsupported=tuple(dict.fromkeys(build.unsupported)),
    )
