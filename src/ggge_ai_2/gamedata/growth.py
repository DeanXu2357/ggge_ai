"""Growth model of the game data: see docs/reference/growth-model.md."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

RATE_SCALE = 10_000


@dataclass(frozen=True)
class GrowthTables:
    level_curve: Mapping[int, int]
    limit_break_rate_percent: Mapping[int, int]
    rarity_level_cap: Mapping[int, int]

    @property
    def max_level(self) -> int:
        return max(self.level_curve)


def level_rate(tables: GrowthTables, level: int) -> int:
    if level < 1:
        raise ValueError(f"level below 1: {level}")
    return tables.level_curve[min(level, tables.max_level)]


def level_value(tables: GrowthTables, base: int, max_value: int, level: int) -> int:
    return base + (max_value - base) * level_rate(tables, level) // RATE_SCALE


def level_cap(tables: GrowthTables, rarity: int, *, uncapped: bool = False) -> int:
    if uncapped:
        return tables.max_level
    try:
        return tables.rarity_level_cap[rarity]
    except KeyError:
        raise ValueError(f"unknown rarity: {rarity}") from None


def limit_break_value(tables: GrowthTables, value: int, step: int) -> int:
    try:
        rate_percent = tables.limit_break_rate_percent[step]
    except KeyError:
        raise ValueError(f"unknown limit break step: {step}") from None
    return value * rate_percent // 100


def supporter_bonus(max_addition: int, correction_rate: int) -> int:
    return max_addition * correction_rate // RATE_SCALE


def weapon_value(base: int, rate_percent: int) -> int:
    return base * rate_percent // 100
