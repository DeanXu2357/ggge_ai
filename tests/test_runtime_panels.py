"""Panel parsing pinned to hand-transcribed fixtures.

Expected values were transcribed field by field off the fixture images. The
weapon-card cases deliberately cover the three layout variants the game
actually ships: a plain card, a card carrying an effect note (one row taller),
and an ammunition card (seven columns instead of six).
"""

from __future__ import annotations

import functools
from pathlib import Path

import cv2
import pytest

from ggge_ai.runtime import panels
from ggge_ai.runtime.panels import PanelKind

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "vision"


@functools.cache
def frame(name: str):
    image = cv2.imread(str(FIXTURES / f"{name}.png"))
    assert image is not None, name
    return image


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("stage_panels/enemy_detail_basicinfo_unicorngundam", PanelKind.STAGE_BASIC),
        ("stage_panels/enemy_detail_stats_gearadoga", PanelKind.STAGE_BASIC),
        ("stage_panels/ally_detail_basicinfo_ntgundam", PanelKind.STAGE_BASIC),
        ("stage_panels/enemy_detail_combo_unicorngundam", PanelKind.STAGE_COMBO),
        ("stage_panels/enemy_detail_weapons_kshatriya", PanelKind.STAGE_WEAPONS),
        ("stage_panels/enemy_detail_skills_unicorngundam", PanelKind.STAGE_WEAPONS),
        ("stage_panels/ally_detail_weapons_ntgundam", PanelKind.STAGE_WEAPONS),
        ("stage_panels/enemy_detail_abilities_gearadoga", PanelKind.STAGE_ABILITIES),
        ("stage_panels/ally_detail_abilities_ntgundam", PanelKind.STAGE_ABILITIES),
        ("roster_panels/unit_detail_nu_gundam_info_shield", PanelKind.ROSTER_UNIT_INFO),
        ("roster_panels/unit_weapons_theo_top", PanelKind.ROSTER_UNIT_WEAPONS),
        ("roster_panels/unit_weapons_map_icon_nu_gundam", PanelKind.ROSTER_UNIT_WEAPONS),
        ("roster_panels/pilot_detail_amuro_info", PanelKind.ROSTER_PILOT),
        ("roster_panels/pilot_skills_amuro", PanelKind.ROSTER_PILOT),
        ("stage_panels/prep_screen", PanelKind.UNKNOWN),
        ("stage_panels/battle_map_turn1", PanelKind.UNKNOWN),
        ("stage_panels/enemy_summary_card", PanelKind.UNKNOWN),
        ("roster_panels/unit_stats_theo_lv10", PanelKind.UNKNOWN),
        ("roster_panels/support_stats_riariff", PanelKind.UNKNOWN),
    ],
)
def test_classify(name, kind):
    assert panels.classify(frame(name)) is kind


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (
            "stage_panels/enemy_detail_weapons_gearadoga",
            (29265, 424, 4, 4078, 3637, 4877, 326, 326, 292, 327, 281, 15),
        ),
        (
            "stage_panels/enemy_detail_weapons_unicorngundam",
            (109440, 750, 4, 8064, 6019, 5455, 583, 700, 690, 525, 614, 15),
        ),
        (
            "stage_panels/ally_detail_weapons_ntgundam",
            (39955, 131, 5, 4809, 3699, 3978, 113, 112, 79, 141, 92, 15),
        ),
        (
            "stage_panels/enemy_detail_combo_unicorngundam",
            (109440, 750, 4, 8064, 6019, 5455, 583, 700, 690, 525, 614, 15),
        ),
    ],
)
def test_stage_stat_column(name, expected):
    column = panels.read_stat_column(frame(name))
    assert column is not None
    read = tuple(column.absolute(field) for field, _ in column.slots())
    assert read == expected
    assert column.deltas == ()


def test_roster_stat_column_has_no_pilot_block():
    column = panels.read_stat_column(frame("roster_panels/unit_weapons_theo_top"))
    assert column is not None
    assert (
        column.absolute("max_hp"),
        column.absolute("en_max"),
        column.absolute("move_range"),
        column.absolute("unit_attack"),
        column.absolute("unit_defense"),
        column.absolute("mobility"),
    ) == (14847, 136, 5, 1647, 1488, 1705)
    assert column.absolute("pilot_shooting") is None


def test_abilities_tab_stat_column_reports_deltas_not_stats():
    column = panels.read_stat_column(frame("stage_panels/ally_detail_abilities_ntgundam"))
    assert column is not None
    assert column.deltas == ("max_hp", "unit_attack", "unit_defense", "mobility")
    assert column.absolute("max_hp") is None
    assert column.absolute("en_max") == 131


def test_basic_view_has_no_stat_column():
    assert panels.read_stat_column(frame("stage_panels/enemy_detail_basicinfo_unicorngundam")) is None


WEAPON_CASES = {
    "stage_panels/enemy_detail_weapons_gearadoga": [
        (("shooting",), 1, 1, 3, False, 3600, 29, 100, 0, None, False, False),
        (("shooting",), 1, 1, 3, False, 3200, 25, 100, 0, None, False, False),
    ],
    "stage_panels/enemy_detail_weapons_kshatriya": [
        (("melee",), 1, 1, 1, False, 3500, 25, 105, 10, None, False, False),
        (("shooting",), 1, 1, 4, False, 4100, 33, 105, 0, None, False, False),
        (("awakening",), 1, 2, 4, False, 3800, 31, 95, 20, None, False, True),
    ],
    "stage_panels/enemy_detail_weapons_unicorngundam": [
        (("melee",), 1, 1, 1, False, 3500, 25, 110, 10, None, False, False),
        (("shooting",), 1, 2, 3, False, 3800, 29, 110, 0, None, False, False),
        (("shooting",), 1, 2, 4, False, 4200, 35, 100, 0, None, False, True),
    ],
    "stage_panels/ally_detail_weapons_ntgundam": [
        (("melee",), 1, 1, 2, False, 3600, 29, 100, 5, None, False, True),
        (("shooting",), 1, 1, 3, False, 3400, 25, 100, 0, None, False, False),
    ],
    "roster_panels/unit_weapons_theo_top": [
        (("melee",), 1, 1, 1, False, 3400, 22, 100, 5, None, False, False),
        (("awakening",), 1, 1, 3, False, 4500, 37, 105, 10, None, False, True),
        (("shooting",), 1, 2, 4, False, 3300, 22, 100, 0, None, False, False),
    ],
    "roster_panels/unit_weapons_map_full_armor_gundam": [
        (("shooting",), 3, None, None, True, 3960, 60, 100, 0, 1, True, True),
        (("melee",), 4, 1, 1, False, 3910, 23, 100, 10, None, False, False),
        (("shooting",), 5, 2, 4, False, 4440, 26, 100, 0, None, False, True),
    ],
    "roster_panels/unit_weapons_map_icon_nu_gundam": [
        (("awakening",), 1, None, None, True, 3900, 50, 105, 0, 1, True, True),
        (("melee",), 1, 1, 1, False, 3400, 22, 105, 5, None, False, False),
        (("melee", "shooting", "awakening"), 1, 1, 4, False, 5200, 47, 105, 0, None, False, True),
    ],
}


@pytest.mark.parametrize("name", sorted(WEAPON_CASES))
def test_weapon_rows(name):
    rows = panels.read_weapon_rows(frame(name))
    read = [
        (
            tuple(sorted(row.categories)),
            row.level,
            row.range_min,
            row.range_max,
            row.map_weapon,
            row.power,
            row.en_cost,
            row.hit_pct,
            row.crit_pct,
            row.ammo,
            row.has_ammo_column,
            row.note_region is not None,
        )
        for row in rows
    ]
    expected = [(tuple(sorted(case[0])), *case[1:]) for case in WEAPON_CASES[name]]
    assert read == expected


def test_scrolled_card_is_reported_clipped():
    """enemy_detail_skills_unicorngundam is the same tab scrolled down: the top
    card shows its stat row but its name plate is above the viewport."""
    rows = panels.read_weapon_rows(frame("stage_panels/enemy_detail_skills_unicorngundam"))
    assert [row.clipped for row in rows] == [True, False]
    assert rows[0].categories == ()


def test_weapon_rows_only_on_the_weapon_tab():
    assert panels.read_weapon_rows(frame("stage_panels/enemy_detail_abilities_kshatriya")) == []
    assert panels.read_weapon_rows(frame("stage_panels/enemy_detail_combo_unicorngundam")) == []


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (
            "stage_panels/enemy_detail_basicinfo_unicorngundam",
            (109440, 750, 4, None, "enemy", None, 15, 0, 12, 1),
        ),
        (
            "stage_panels/enemy_detail_stats_gearadoga",
            (29265, 424, 4, None, "enemy", None, 15, 0, 12, 1),
        ),
        (
            "stage_panels/enemy_detail_stats_kshatriya",
            (167817, 594, 4, None, "enemy", None, 15, 0, 12, 1),
        ),
        (
            "stage_panels/ally_detail_basicinfo_ntgundam",
            (39955, 131, 5, 51, "ally", 22, 15, 0, 12, 1),
        ),
    ],
)
def test_basic_view(name, expected):
    view = panels.read_basic_view(frame(name))
    assert view is not None
    assert (
        view.max_hp,
        view.en_max,
        view.move_range,
        view.unit_lv,
        view.faction,
        view.pilot_lv,
        view.pilot_sp,
        view.mp_current,
        view.mp_max,
        view.chance_step_badges,
    ) == expected


def test_basic_view_only_on_the_basic_view():
    assert panels.read_basic_view(frame("stage_panels/enemy_detail_weapons_kshatriya")) is None


def test_ammunition_card_reflows_the_header():
    strips = panels.header_strips(frame("roster_panels/unit_weapons_map_icon_nu_gundam"))
    cells = panels.header_cells(frame("roster_panels/unit_weapons_map_icon_nu_gundam"), strips[0][0])
    assert len(cells) == 7
    plain = panels.header_cells(frame("roster_panels/unit_weapons_map_icon_nu_gundam"), strips[1][0])
    assert len(plain) == 6
