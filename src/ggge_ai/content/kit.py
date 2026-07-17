"""Unit kit data: transcription shapes, the combat spec, and defaults.

UnitStats and WeaponRow are the shapes a unit-detail panel transcribes
into (battle.panels does the pixel reading; stage definition files store
these shapes verbatim). UnitSpec is the combat-number bundle everything
downstream grounds on, and SpecDefaults fills the holes a spec leaves --
assumptions, not game content, and every use is reported by the
grounding layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..sim import SimWeapon


@dataclass(frozen=True)
class UnitStats:
    hp: int | None
    en: int | None
    move_range: int | None
    unit_attack: int | None
    unit_defense: int | None
    unit_mobility: int | None
    pilot_shooting: int | None
    pilot_melee: int | None
    pilot_awakening: int | None
    pilot_defense: int | None
    pilot_reaction: int | None
    sp: int | None


@dataclass(frozen=True)
class WeaponRow:
    kind: str | None
    level: int | None
    range_min: int | None
    range_max: int | None
    power: int | None
    en_cost: int | None
    hit_pct: int | None
    crit_pct: int | None


@dataclass(frozen=True)
class UnitSpec:
    """Combat numbers for one unit, from panel OCR or the content cache.

    None means "not read yet"; grounding falls back to SpecDefaults and
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
class SpecDefaults:
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


def to_unit_spec(stats: UnitStats, rows: list[WeaponRow]) -> tuple[UnitSpec, list[str]]:
    """Panel readings -> UnitSpec plus the assumptions the conversion made.
    Unreadable weapon rows are dropped (an inert weapon would poison damage
    search); every drop is reported."""
    assumptions: list[str] = []
    weapons: list[SimWeapon] = []
    for i, row in enumerate(rows, start=1):
        if row.power is None:
            assumptions.append(f"weapon {i}: power unreadable, row dropped")
            continue
        if row.range_min is None or row.range_max is None:
            assumptions.append(f"weapon {i}: range unreadable, assuming 1-1")
        weapons.append(
            SimWeapon(
                name=f"weapon_{i}" + (f"_{row.kind}" if row.kind else ""),
                power=float(row.power),
                range_min=row.range_min if row.range_min is not None else 1,
                range_max=row.range_max if row.range_max is not None else 1,
                en_cost=row.en_cost if row.en_cost is not None else 0,
            )
        )
    return (
        UnitSpec(
            max_hp=stats.hp,
            en_max=stats.en,
            unit_attack=float(stats.unit_attack) if stats.unit_attack is not None else None,
            unit_defense=float(stats.unit_defense) if stats.unit_defense is not None else None,
            pilot_defense=float(stats.pilot_defense) if stats.pilot_defense is not None else None,
            reaction=float(stats.pilot_reaction) if stats.pilot_reaction is not None else None,
            mobility=float(stats.unit_mobility) if stats.unit_mobility is not None else None,
            move_range=stats.move_range,
            pilot_shooting=float(stats.pilot_shooting)
            if stats.pilot_shooting is not None
            else None,
            pilot_melee=float(stats.pilot_melee) if stats.pilot_melee is not None else None,
            weapons=tuple(weapons),
        ),
        assumptions,
    )


def pilot_attack_for(spec: UnitSpec, kind: str | None) -> float | None:
    """The pilot stat a weapon of `kind` attacks with; falls back to the
    generic pilot_attack when the kind is unknown or the stat unread."""
    if kind == "shooting" and spec.pilot_shooting is not None:
        return spec.pilot_shooting
    if kind == "melee" and spec.pilot_melee is not None:
        return spec.pilot_melee
    return spec.pilot_attack
