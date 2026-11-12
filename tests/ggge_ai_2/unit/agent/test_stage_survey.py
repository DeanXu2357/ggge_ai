from __future__ import annotations

from dataclasses import replace

import numpy as np

from ggge_ai_2.agent.stage_survey import differences, stage_data
from ggge_ai_2.mapgeom import contract as geo
from ggge_ai_2.stagedata import contract as stage

STAGE = "story-1-1-hard"


def mask(seed: int) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 2, (14, 60), np.uint8) * 255


def brief(seed: int, hp: int = 5000) -> geo.UnitBrief:
    return geo.UnitBrief(
        mech_role=geo.UnitRole.ATTACK,
        mech_name=geo.NameMask(mask(seed)),
        hp=hp,
        en=120,
        pilot_role=geo.UnitRole.NO_ROLE,
        pilot_name=geo.NameMask(mask(seed + 1000)),
        mp=30,
        mp_max=40,
        state=geo.PilotState.STRONG,
    )


def judgment(
    unit_cells: dict[geo.MapCell, geo.UnitId], units: dict[geo.UnitId, geo.MapUnit]
) -> geo.MapJudgment:
    return geo.MapJudgment(
        stage=None,
        turn=1,
        phase=geo.ViewPhase.PLAYER,
        columns=geo.Axis(6, True, True),
        rows=geo.Axis(4, True, True),
        cells={},
        uncertain=frozenset(),
        unit_cells=unit_cells,
        units=units,
        current=frozenset(),
    )


def enemy(seed: int = 1, hp: int = 5000) -> geo.MapUnit:
    return geo.MapUnit(False, geo.Faction.ENEMY, brief(seed, hp))


def surveyed(found: geo.MapJudgment, code_version: str = "9416000a") -> stage.StageData:
    return stage_data(found, STAGE, "1.4.0", code_version)


def test_the_stage_data_takes_the_map_size_and_the_versions():
    data = surveyed(judgment({}, {}))

    assert (data.stage, data.app_version, data.code_version) == (STAGE, "1.4.0", "9416000a")
    assert (data.columns, data.rows) == (6, 4)
    assert (data.terrain, data.deploy_cells, data.victory, data.events) == ({}, (), (), ())


def test_the_stage_data_keeps_only_the_units_that_the_player_does_not_control():
    sortie = geo.MapUnit(True, None, None)

    data = surveyed(judgment({(1, 1): 0, (4, 2): 1}, {0: enemy(), 1: sortie}))

    assert [unit.pos for unit in data.units] == [(1, 1)]


def test_a_unit_takes_its_top_left_cell_and_its_size():
    cells = {(2, 1): 0, (3, 1): 0, (2, 2): 0, (3, 2): 0}

    (unit,) = surveyed(judgment(cells, {0: enemy()})).units

    assert (unit.pos, unit.size) == ((2, 1), (2, 2))


def test_a_unit_without_the_enemy_faction_is_an_ally():
    npc = geo.MapUnit(False, None, brief(2))

    (unit,) = surveyed(judgment({(0, 0): 0}, {0: npc})).units

    assert unit.faction is stage.Faction.ALLY


def test_the_brief_takes_the_stage_types():
    (unit,) = surveyed(judgment({(0, 0): 0}, {0: enemy(3)})).units

    assert (unit.faction, unit.controllable) == (stage.Faction.ENEMY, False)
    assert (unit.brief.mech_role, unit.brief.pilot_role, unit.brief.state) == (
        stage.UnitRole.ATTACK,
        stage.UnitRole.NO_ROLE,
        stage.PilotState.STRONG,
    )
    assert (unit.brief.hp, unit.brief.en, unit.brief.mp, unit.brief.mp_max) == (5000, 120, 30, 40)
    assert np.array_equal(unit.brief.mech_name.mask, mask(3))
    assert np.array_equal(unit.brief.pilot_name.mask, mask(1003))


def test_the_units_are_in_reading_order():
    data = surveyed(
        judgment({(4, 0): 0, (1, 2): 1, (2, 0): 2}, {0: enemy(), 1: enemy(), 2: enemy()})
    )

    assert [unit.pos for unit in data.units] == [(2, 0), (4, 0), (1, 2)]


def test_two_surveys_of_one_board_have_no_difference():
    found = judgment({(1, 1): 0}, {0: enemy()})

    assert differences(surveyed(found), surveyed(found)) == ()


def test_another_code_version_is_no_difference():
    found = judgment({(1, 1): 0}, {0: enemy()})

    assert differences(surveyed(found, "aaaaaaaa"), surveyed(found, "bbbbbbbb")) == ()


def test_a_name_crop_that_moves_by_one_pixel_is_no_difference():
    moved = brief(1)
    moved = replace(moved, mech_name=geo.NameMask(np.roll(mask(1), 1, axis=1)))
    old = surveyed(judgment({(1, 1): 0}, {0: enemy()}))

    new = surveyed(judgment({(1, 1): 0}, {0: geo.MapUnit(False, geo.Faction.ENEMY, moved)}))

    assert differences(old, new) == ()


def test_another_map_size_is_a_difference():
    old = surveyed(judgment({}, {}))
    new = replace(old, columns=7)

    assert differences(old, new) == ("columns: 6 -> 7",)


def test_a_missing_and_a_new_unit_are_differences():
    old = surveyed(judgment({(1, 1): 0}, {0: enemy()}))
    new = surveyed(judgment({(2, 2): 0}, {0: enemy()}))

    assert differences(old, new) == ("unit (1, 1): missing", "unit (2, 2): new")


def test_another_hp_is_a_difference():
    old = surveyed(judgment({(1, 1): 0}, {0: enemy(hp=5000)}))
    new = surveyed(judgment({(1, 1): 0}, {0: enemy(hp=5100)}))

    assert differences(old, new) == ("unit (1, 1): hp 5000 -> 5100",)


def test_another_name_is_a_difference():
    old = surveyed(judgment({(1, 1): 0}, {0: enemy(1)}))
    new = surveyed(judgment({(1, 1): 0}, {0: enemy(2)}))

    assert differences(old, new) == (
        "unit (1, 1): mech_name differs",
        "unit (1, 1): pilot_name differs",
    )
