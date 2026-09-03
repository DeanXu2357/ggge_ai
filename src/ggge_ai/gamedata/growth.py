"""Growth model of the game data: see docs/reference/growth-model.md."""

from __future__ import annotations

LEVEL_CURVE: tuple[int, ...] = (
    0, 102, 204, 306, 408, 510, 612, 714, 816, 918,
    1020, 1122, 1224, 1326, 1428, 1530, 1632, 1734, 1836, 1938,
    2040, 2142, 2244, 2346, 2448, 2550, 2652, 2754, 2856, 2958,
    3060, 3162, 3264, 3366, 3468, 3570, 3672, 3774, 3876, 3978,
    4080, 4181, 4282, 4383, 4484, 4585, 4686, 4787, 4888, 4989,
    5090, 5191, 5292, 5393, 5494, 5595, 5696, 5797, 5898, 6000,
    6100, 6200, 6300, 6400, 6500, 6600, 6700, 6800, 6900, 7000,
    7100, 7200, 7300, 7400, 7500, 7600, 7700, 7800, 7900, 8000,
    8100, 8200, 8300, 8400, 8500, 8600, 8700, 8800, 8900, 9000,
    9100, 9200, 9300, 9400, 9500, 9600, 9700, 9800, 9900, 10000,
)
RATE_SCALE = 10_000
RARITY_LEVEL_CAP: dict[int, int] = {1: 60, 2: 70, 3: 80, 4: 90, 5: 100}
LIMIT_BREAK_RATE_PERCENT: dict[int, int] = {0: 100, 1: 120, 2: 130, 3: 140}
MAX_LEVEL = 100


def level_rate(level: int) -> int:
    if level < 1:
        raise ValueError(f"level below 1: {level}")
    return LEVEL_CURVE[min(level, MAX_LEVEL) - 1]


def level_value(base: int, max_value: int, level: int) -> int:
    return base + (max_value - base) * level_rate(level) // RATE_SCALE


def level_cap(rarity: int, *, uncapped: bool = False) -> int:
    if uncapped:
        return MAX_LEVEL
    try:
        return RARITY_LEVEL_CAP[rarity]
    except KeyError:
        raise ValueError(f"unknown rarity: {rarity}") from None


def limit_break_value(value: int, step: int) -> int:
    try:
        rate_percent = LIMIT_BREAK_RATE_PERCENT[step]
    except KeyError:
        raise ValueError(f"unknown limit break step: {step}") from None
    return value * rate_percent // 100


def supporter_bonus(max_addition: int, correction_rate: int) -> int:
    return max_addition * correction_rate // RATE_SCALE


def weapon_value(base: int, rate_percent: int) -> int:
    return base * rate_percent // 100


def level_curve_rows() -> list[tuple[int, int]]:
    return [(level, LEVEL_CURVE[level - 1]) for level in range(1, MAX_LEVEL + 1)]


def limit_break_rate_rows() -> list[tuple[int, int]]:
    return sorted(LIMIT_BREAK_RATE_PERCENT.items())


def rarity_level_cap_rows() -> list[tuple[int, int]]:
    return sorted(RARITY_LEVEL_CAP.items())
