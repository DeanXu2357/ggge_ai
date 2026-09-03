"""The normalizer turns a datamine dump into schema rows (issue #92).

The recorded slice in tests/fixtures/datamine/ carries the same file names as a
dump, so the reader takes it as it is.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ggge_ai.gamedata.normalize import COLUMNS, Dump, normalize, raw_rows

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "datamine"
STAMP = "202609010310"
ZEONG = 1001003000
ZEONG_SSP_WEAPON = 100100300090


def _payload(name: str) -> object:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rows():
    return normalize(STAMP, Dump.read(FIXTURES))


def _table(rows, name: str) -> list[tuple]:
    return rows.tables[name]


def _column(name: str, column: str) -> int:
    return COLUMNS[name].index(column)


def test_every_row_matches_the_column_list_of_its_table(rows):
    for table, table_rows in rows.tables.items():
        assert table in COLUMNS, table
        for row in table_rows:
            assert len(row) == len(COLUMNS[table]), table


def test_the_unit_table_holds_every_unit_of_the_dump(rows):
    units = _table(rows, "unit")
    ids = [row[_column("unit", "id")] for row in units]

    assert sorted(ids) == [1001000100, 1001000150, ZEONG, 1001003050]
    zeong = next(row for row in units if row[_column("unit", "id")] == ZEONG)
    assert zeong[_column("unit", "rarity")] == 4
    assert zeong[_column("unit", "ult")] is False


def test_the_unit_stat_rows_carry_the_base_and_the_sp_values(rows):
    stats = next(row["stats"] for row in _payload("unit") if row["id"] == ZEONG)
    hp = next(row for row in _table(rows, "unit_stat") if row[1] == ZEONG and row[2] == "hp")

    assert hp == (STAMP, ZEONG, "hp", stats["hp"], stats["max_hp"], 8936, 64337)
    assert (stats["hp"], stats["max_hp"]) == (8032, 57831)
    assert len([row for row in _table(rows, "unit_stat") if row[1] == ZEONG]) == 6


def test_the_ssp_stat_rows_carry_the_ssp_addition(rows):
    hp = next(row for row in _table(rows, "unit_ssp_stat") if row[1] == ZEONG and row[2] == "hp")

    assert hp[_column("unit_ssp_stat", "max")] == 4577


def test_the_initial_release_is_the_core_of_level_zero(rows):
    cores = [row for row in _table(rows, "unit_ssp_core") if row[1] == ZEONG]

    assert [row[2] for row in cores] == [0, 1, 5, 10, 15, 20]
    assert cores[0] == (STAMP, ZEONG, 0, 0, 0)


def test_the_ssp_releases_keep_the_core_order_and_the_payload_of_every_kind(rows):
    releases = [row for row in _table(rows, "unit_ssp_release") if row[1] == ZEONG]

    assert [(row[2], row[3], row[4]) for row in releases] == [
        (0, 1, "ability_change"),
        (1, 1, "weapon_change"),
        (1, 2, "weapon_enhance"),
        (5, 1, "terrain"),
        (10, 1, "weapon_effect"),
        (10, 2, "weapon_enhance"),
    ]
    payload = _column("unit_ssp_release", "payload")
    assert releases[1][payload]["after_weapon_id"] == ZEONG_SSP_WEAPON
    assert releases[2][payload]["target_weapon_id"] == 100100300002
    assert releases[2][payload]["weapon_enhance_type_index"] == 1
    assert releases[2][payload]["effect_value"] == 175


def test_an_unknown_release_function_type_stops_the_normalizer():
    units = _payload("unit")
    zeong = next(row for row in units if row["id"] == ZEONG)
    zeong["ssp_config"]["initial_release"]["release_function_type_index"] = 99
    dump = Dump.read(FIXTURES)

    with pytest.raises(ValueError, match="99"):
        normalize(STAMP, Dump(units, dump.weapon, [], [], []))


def test_the_unit_ability_sort_runs_from_one_without_a_gap(rows):
    for unit in _payload("unit"):
        sorts = [row[2] for row in _table(rows, "unit_ability") if row[1] == unit["id"]]
        assert sorts == list(range(1, len(unit["abilities"]) + 1))


def test_the_weapon_table_holds_every_weapon_of_the_container(rows):
    weapons = _table(rows, "weapon")
    ssp = next(row for row in weapons if row[1] == ZEONG_SSP_WEAPON)

    assert len(weapons) == 16
    assert ssp[_column("weapon", "is_ssp")] is True
    assert ssp[_column("weapon", "power")] == 4900
    assert ssp[_column("weapon", "en")] == 61
    assert ssp[_column("weapon", "range_min")] == 2
    assert ssp[_column("weapon", "range_max")] == 5
    assert ssp[_column("weapon", "hit_rate")] == 105
    assert ssp[_column("weapon", "critical_rate")] == 20


def test_every_weapon_carries_five_growth_levels(rows):
    growth = _table(rows, "weapon_growth")
    per_weapon = {row[1] for row in growth}
    level_five = next(row for row in growth if row[1] == ZEONG_SSP_WEAPON and row[2] == 5)

    assert len(growth) == 5 * len(per_weapon)
    assert level_five[_column("weapon_growth", "power_rate")] == 120
    assert level_five[_column("weapon_growth", "en_rate")] == 90


def test_the_weapon_traits_keep_a_one_based_sort_over_the_levels(rows):
    traits = [row for row in _table(rows, "weapon_trait") if row[1] == 100100010003]

    assert [row[2] for row in traits] == list(range(1, len(traits) + 1))
    assert [row[3] for row in traits if row[4] == 300030101] == [1, 2]


def test_the_pilot_tables_hold_every_pilot_and_its_five_stats(rows):
    pilots = _payload("character")

    assert len(_table(rows, "pilot")) == 3
    assert len(_table(rows, "pilot_stat")) == 15
    assert len(_table(rows, "pilot_skill")) == sum(len(row["skills"]) for row in pilots)
    payload = _column("pilot_skill", "payload")
    assert any(row[payload] is None for row in _table(rows, "pilot_skill"))


def test_the_tag_table_is_the_sorted_union_of_the_unit_and_pilot_tags(rows):
    ids = [row[1] for row in _table(rows, "tag")]

    assert ids == sorted(set(ids))
    assert {row[2] for row in _table(rows, "unit_tag")} <= set(ids)
    assert {row[2] for row in _table(rows, "pilot_tag")} <= set(ids)


def test_the_support_crew_tables_hold_the_additions_and_the_growth_table(rows):
    crews = _table(rows, "supporter")

    assert crews == [(STAMP, 1001000150, "Bright Noa & White Base", 5, 2000, 300)]
    assert [row[2] for row in _table(rows, "supporter_limit_break")] == [0, 1, 2, 3]
    growth = _table(rows, "supporter_growth")
    assert len(growth) == 400
    assert growth[0] == (STAMP, 1, 0, 2000)
    assert growth[-1] == (STAMP, 100, 3, 14000)


def test_the_raw_rows_key_every_source_row(rows):
    units = raw_rows(STAMP, "unit", _payload("unit"))
    weapons = raw_rows(STAMP, "weapon", _payload("weapon"))
    formula = raw_rows(STAMP, "formula", {"lines": [], "notes": []})

    assert [row[2] for row in units] == [str(row["id"]) for row in _payload("unit")]
    assert {row[1] for row in units} == {"unit"}
    assert len([row for row in weapons if row[1] == "weapon"]) == 16
    assert len([row for row in weapons if row[1] == "weapon_unit"]) == 4
    assert [row[1:3] for row in formula] == [("formula", "formula")]


def test_two_source_rows_that_share_a_key_stop_the_raw_rows():
    twice = [{"id": 7, "name": "first"}, {"id": 7, "name": "second"}]

    with pytest.raises(ValueError, match="character.*7"):
        raw_rows(STAMP, "character", twice)
