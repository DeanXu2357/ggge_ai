"""畫面辨識：真截圖上的分類、AUTO 三態、設定頁探針、整幀指紋。"""

from __future__ import annotations

import numpy as np
import pytest

from ggge_ai.runtime import screens
from tests.fixtures.frames import load, paste

AUTO_BOX = (1770, 15, 190, 75)


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("stage_panels/battle_map_turn1_r2", screens.BATTLE_MAP),
        ("stage_panels/battle_map_turn1", screens.BATTLE_MAP),
        ("grid/hub_grid_on_20260719", screens.BATTLE_MAP),
        ("grid/hub_gridless_20260719", screens.BATTLE_MAP),
        ("forecast/our_turn_unit_list_20260719", screens.BATTLE_MAP),
        ("mode_label/dark_our_turn_hub", screens.BATTLE_MAP),
        ("mode_label/enemy_turn_banner_not_ours", screens.BATTLE_MAP_ENEMY),
        ("mode_label/dark_unit_move", screens.BATTLE_UNIT_MOVE),
        ("mode_label/snow_bright_unit_move", screens.BATTLE_UNIT_MOVE),
        ("mode_label/dark_weapon_select", screens.BATTLE_WEAPON_SELECT),
        ("forecast/map_weapon_20260719", screens.BATTLE_WEAPON_SELECT),
        ("forecast/reaction_live_20260719", screens.BATTLE_PREP_REACTION),
        ("forecast/reaction_menu_20260719", screens.BATTLE_PREP_REACTION),
        ("forecast/attack_support_20260719", screens.BATTLE_PREP),
        ("mode_label/dark_battle_prep", screens.BATTLE_PREP),
        ("forecast/unit_detail_combined_20260719", screens.UNIT_DETAIL),
        ("stage_panels/enemy_detail_weapons_kshatriya", screens.UNIT_DETAIL),
        ("stage_panels/stage_info_conditions", screens.STAGE_INFO),
        ("stage_panels/prep_screen", screens.SORTIE_PREP),
        ("popups/login_bonus_dim_20260729", screens.LOGIN_BONUS),
        ("popups/notice_loading_20260729", screens.NOTICE),
        ("popups/date_changed_hub_20260730", screens.DATE_CHANGED),
        ("popups/stage_list_dim_20260719", screens.STAGE_LIST),
    ],
)
def test_the_classifier_names_the_screen(case, expected):
    assert screens.classify(load(case)) == expected


def test_the_login_popups_beat_whatever_they_are_covering():
    """三個系統彈窗都是全幀覆蓋物，group 0：底下是地圖或主選單都不該勝出。
    這四張都是模板來源之外的幀（褪色中的 LOGIN BONUS、載入中的公告、hub 底的
    日期對話框、暗掉的關卡列表），所以是留出樣本不是自我對照。"""
    for case, expected in (
        ("popups/login_bonus_dim_20260729", screens.LOGIN_BONUS),
        ("popups/notice_loading_20260729", screens.NOTICE),
        ("popups/date_changed_hub_20260730", screens.DATE_CHANGED),
    ):
        measured = screens.scores(load(case))
        assert measured[expected] >= 0.80, (case, measured[expected])


def test_a_battle_map_is_none_of_the_system_popups():
    measured = screens.scores(load("grid/hub_grid_on_20260719"))

    for name in (screens.LOGIN_BONUS, screens.NOTICE, screens.DATE_CHANGED, screens.STAGE_LIST):
        assert measured[name] < 0.70, name


def test_the_enemy_turn_banner_never_wins_as_our_turn():
    """敵方回合橫幅與我軍回合共用三個字模，raw/highpass 都在任何門檻之上——
    分開靠同組 argmax，不是靠門檻。"""
    ours = screens.scores(load("mode_label/dark_our_turn_hub"))
    theirs = screens.scores(load("mode_label/enemy_turn_banner_not_ours"))

    assert ours[screens.BATTLE_MAP] > ours[screens.BATTLE_MAP_ENEMY] > 0.8
    assert theirs[screens.BATTLE_MAP_ENEMY] > theirs[screens.BATTLE_MAP] > 0.8


def test_a_blank_frame_is_unknown_not_the_closest_thing():
    assert screens.classify(np.zeros((1080, 2340, 3), np.uint8)) == screens.UNKNOWN


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("stage_panels/battle_map_turn1_r2", screens.AUTO_OFF),
        ("grid/hub_grid_on_20260719", screens.AUTO_OFF),
        ("stage_panels/stage_info_conditions", screens.AUTO_ON),
        ("stage_panels/battle_map_turn1", screens.AUTO_ACTIVE),
        ("stage_panels/enemy_summary_card", screens.AUTO_ACTIVE),
    ],
)
def test_the_auto_switch_reads_its_three_states(case, expected):
    assert screens.read_auto_switch(load(case)) == expected


@pytest.mark.parametrize(
    ("crop_case", "expected"),
    [
        ("stage_panels/stage_info_auto_off", screens.AUTO_OFF),
        ("stage_panels/stage_info_auto_on", screens.AUTO_ON),
        ("stage_panels/battle_auto_active_red", screens.AUTO_ACTIVE),
    ],
)
def test_the_curated_auto_chip_crops_agree(crop_case, expected):
    import cv2

    from tests.fixtures.frames import path_of

    chip = cv2.imread(str(path_of(crop_case)))
    assert screens.read_auto_switch(paste(chip, AUTO_BOX)) == expected


def test_a_dark_frame_without_the_chip_is_not_read_as_off():
    """OFF 是唯一「不要動它」的答案，所以最貴的誤讀就是把黑幀當 OFF。"""
    assert screens.read_auto_switch(np.zeros((1080, 2340, 3), np.uint8)) is None
    assert screens.read_auto_switch(load("hp_arc/phase_start_clean")) is None


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("forecast/our_turn_unit_list_20260719", screens.ROSTER_EXPANDED),
        ("grid/hub_grid_on_20260719", screens.ROSTER_EXPANDED),
        ("stage_panels/battle_map_turn1", screens.ROSTER_EXPANDED),
        ("forecast/our_turn_list_collapsed_20260719", screens.ROSTER_COLLAPSED),
    ],
)
def test_the_roster_strip_reads_from_where_its_header_sits(case, expected):
    assert screens.read_roster_strip(load(case)) == expected


@pytest.mark.parametrize(
    "case",
    ["forecast/unit_detail_combined_20260719", "stage_panels/prep_screen"],
)
def test_a_covered_or_absent_roster_strip_is_never_read_as_collapsed(case):
    """「被遮住」與「收合」混成同一個答案，實機上換來 41 次空轉循環（0723 輪四）。"""
    assert screens.read_roster_strip(load(case)) is None


def test_the_settings_page_probes_read_the_grid_toggle_and_the_auto_hexagon():
    frame = load("settings/grid_on_20260706")

    assert screens.read_grid_setting(frame) == "on"
    assert screens.is_auto_battle_off(frame) is True
    assert screens.is_battle_tab_selected(frame) is True
    assert screens.classify(frame) == screens.BATTLE_SETTINGS


def test_a_map_is_not_the_settings_page():
    frame = load("grid/hub_gridless_20260719")

    assert screens.read_grid_setting(frame) is None
    assert screens.is_battle_tab_selected(frame) is False


def test_the_battle_tab_underline_is_a_line_not_a_pixel():
    """單點探針會被鮭色地形斑點誤命中（0721 收斂的 9 幀語料）。"""
    assert screens.is_battle_tab_selected(load("settings/hub_battletab_fp_20260705")) is False


def test_the_red_attack_range_block_is_not_the_battle_tab_underline():
    """紅色攻擊範圍塊湊得出「整列鮭色＋護欄乾淨」，端點對不上才擋得住（0805 南緣讀卡）。"""
    frame = load("settings/hub_redrange_battletab_fp_20260805")

    assert screens.is_battle_tab_selected(frame) is False


def test_the_frame_signature_is_stable_and_discriminating():
    a = load("grid/hub_grid_on_20260719")
    b = load("grid/hub_grid_on_panned_20260719")

    assert screens.frame_signature(a) == screens.frame_signature(a.copy())
    assert screens.frame_signature(a) != screens.frame_signature(b)


def test_the_frame_signature_survives_a_single_pixel_of_animation():
    frame = load("grid/hub_grid_on_20260719")
    nudged = frame.copy()
    nudged[500, 500] = (0, 0, 0)

    assert screens.frame_signature(frame) == screens.frame_signature(nudged)


def test_the_abandon_dialog_probe_separates_the_dialog_from_the_battle_menu():
    """戰鬥選單也是白面板，只有本體平坦度與確認鈕的藍分得開（0804 實機幀）。"""
    assert screens.is_abandon_confirm_dialog(load("popups/abandon_confirm_20260804")) is True
    assert screens.is_abandon_confirm_dialog(load("popups/battle_menu_20260804")) is False
    assert screens.is_abandon_confirm_dialog(load("grid/hub_grid_on_20260719")) is False
