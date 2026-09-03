"""Records that the store reads out of the game data schema."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StatRow:
    base: int
    max: int
    sp_base: int
    sp_max: int


@dataclass(frozen=True)
class SspStat:
    base: int
    max: int


@dataclass(frozen=True)
class SspRelease:
    core_level: int
    sort_order: int
    kind: str
    target_id: int
    payload: dict


@dataclass(frozen=True)
class WeaponGrowth:
    power_rate: int
    en_rate: int
    hit_rate_rate: int
    crit_rate_rate: int


@dataclass(frozen=True)
class WeaponRecord:
    id: int
    unit_id: int
    name: str
    type: int
    work_type: int
    attack_attr: int
    weapon_attr: int
    power: int
    en: int
    hit_rate: int
    critical_rate: int
    range_min: int
    range_max: int
    ammo: int
    is_ssp: bool
    growth: dict[int, WeaponGrowth] = field(default_factory=dict)


@dataclass(frozen=True)
class UnitRecord:
    id: int
    name: str
    rarity: int
    ult: bool
    stats: dict[str, StatRow]
    ssp_stats: dict[str, SspStat]
    releases: tuple[SspRelease, ...]
    weapons: tuple[WeaponRecord, ...]


@dataclass(frozen=True)
class PilotRecord:
    id: int
    name: str
    rarity: int
    stats: dict[str, StatRow]


@dataclass(frozen=True)
class SupporterRecord:
    id: int
    name: str
    rarity: int
    max_hp_addition: int
    max_attack_addition: int
