"""The growth model reproduces the values of the game front end (issue #92).

The worked examples use the recorded datamine slice in tests/fixtures/datamine/.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ggge_ai.gamedata.growth import (
    LEVEL_CURVE,
    LIMIT_BREAK_RATE_PERCENT,
    RARITY_LEVEL_CAP,
    level_cap,
    level_curve_rows,
    level_rate,
    level_value,
    limit_break_rate_rows,
    limit_break_value,
    rarity_level_cap_rows,
    supporter_bonus,
    weapon_value,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "datamine"
ZEONG_HP = 8032
ZEONG_MAX_HP = 57831


def _correction_rate(level: int, limit_break: int) -> int:
    rows = json.loads((FIXTURES / "supporter_growth.json").read_text(encoding="utf-8"))
    for row in rows:
        if row["level"] == level and row["limit_break"] == limit_break:
            return row["correction_rate"]
    raise AssertionError(f"no growth row for level {level} step {limit_break}")


def test_the_level_curve_runs_from_zero_to_the_full_rate_over_a_hundred_levels():
    assert len(LEVEL_CURVE) == 100
    assert LEVEL_CURVE[0] == 0
    assert LEVEL_CURVE[-1] == 10000
    assert list(LEVEL_CURVE) == sorted(LEVEL_CURVE)


def test_the_level_value_spans_the_base_and_the_maximum_and_stops_at_level_one_hundred():
    assert level_value(ZEONG_HP, ZEONG_MAX_HP, 1) == ZEONG_HP
    assert level_value(ZEONG_HP, ZEONG_MAX_HP, 100) == ZEONG_MAX_HP
    assert level_value(ZEONG_HP, ZEONG_MAX_HP, 150) == ZEONG_MAX_HP
    assert level_value(ZEONG_HP, ZEONG_MAX_HP, 50) == 32876


def test_the_level_value_at_the_rarity_cap_of_the_zeong_is_below_the_maximum():
    assert level_value(ZEONG_HP, ZEONG_MAX_HP, level_cap(4)) == 52851


def test_the_support_crew_bonus_grows_with_the_level_and_the_limit_break_step():
    assert supporter_bonus(2000, _correction_rate(1, 0)) == 400
    assert supporter_bonus(300, _correction_rate(1, 0)) == 60
    assert supporter_bonus(2000, _correction_rate(100, 3)) == 2800
    assert supporter_bonus(300, _correction_rate(100, 3)) == 420


def test_the_limit_break_step_raises_the_value_and_an_unknown_step_is_rejected():
    assert limit_break_value(ZEONG_MAX_HP, 0) == ZEONG_MAX_HP
    assert limit_break_value(ZEONG_MAX_HP, 3) == 80963
    with pytest.raises(ValueError):
        limit_break_value(ZEONG_MAX_HP, 4)


def test_the_level_cap_follows_the_rarity_unless_the_unit_is_uncapped():
    assert [level_cap(rarity) for rarity in range(1, 6)] == [60, 70, 80, 90, 100]
    assert level_cap(1, uncapped=True) == 100
    with pytest.raises(ValueError):
        level_cap(6)


def test_the_weapon_value_scales_by_the_rate_percent():
    assert weapon_value(4900, 120) == 5880
    assert weapon_value(61, 90) == 54


def test_the_row_functions_report_the_constant_tables():
    rows = level_curve_rows()

    assert len(rows) == 100
    assert rows[0] == (1, 0)
    assert rows[-1] == (100, 10000)
    assert dict(limit_break_rate_rows()) == LIMIT_BREAK_RATE_PERCENT
    assert dict(rarity_level_cap_rows()) == RARITY_LEVEL_CAP


def test_a_level_below_one_has_no_rate():
    with pytest.raises(ValueError):
        level_rate(0)
