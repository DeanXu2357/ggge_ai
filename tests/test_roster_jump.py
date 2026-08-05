"""名冊跳轉掃描：詳情頁讀值（兩種佈局）、列表格座標、記帳／排程／共現複核。"""

from __future__ import annotations

import numpy as np

from ggge_ai.runtime import jumpscan, roster
from ggge_ai.runtime.coverage import WorldGrid
from tests.fixtures.frames import load

GRID = WorldGrid(phase=(0.0, 0.0), col_pitch=100.0, row_pitch=100.0)


def test_the_enemy_detail_page_reads_its_three_numbers():
    entry = roster.read_detail(load("roster/enemy_detail_20260806"), index=0)

    assert entry == roster.RosterEntry(
        faction=roster.ENEMY, index=0, hp=29265, en=424, mobility=4, lv=None
    )
    assert entry.complete


def test_the_ally_detail_page_has_an_extra_lv_row_and_everything_below_it_shifts():
    entry = roster.read_detail(load("roster/ally_detail_20260806"), index=3)

    assert entry == roster.RosterEntry(
        faction=roster.ALLY, index=3, hp=38311, en=148, mobility=5, lv=55
    )


def test_the_faction_band_is_what_picks_the_layout():
    assert roster.read_faction(load("roster/enemy_detail_20260806")) == roster.ENEMY
    assert roster.read_faction(load("roster/ally_detail_20260806")) == roster.ALLY


def test_a_frame_without_the_faction_band_is_not_a_detail_page():
    blank = np.zeros((1080, 2340, 3), np.uint8)

    assert roster.read_faction(blank) is None
    assert roster.read_detail(blank, index=0) is None


def test_the_ally_list_is_two_rows_of_five_and_the_enemy_list_is_four():
    ally = roster.cell_taps(roster.ALLY)
    enemy = roster.cell_taps(roster.ENEMY)

    assert len(ally) == 10
    assert len(enemy) == 20
    assert ally[0] == enemy[0] == (729, 267)
    assert ally[5] == (729, 513)
    assert enemy[15] == (729, 847)
    assert [x for x, _ in ally[:5]] == [729, 1008, 1286, 1564, 1843]


def test_the_target_is_the_peak_nearest_the_screen_centre():
    peaks = [(300.0, 200.0), (1160.0, 560.0), (2000.0, 900.0)]

    assert jumpscan.target_peak(peaks) == (1160.0, 560.0)
    assert jumpscan.target_peak([]) is None


def _jump(key, cell, offset, peaks):
    return jumpscan.Jump(
        key=key, cell=cell, source=jumpscan.SOURCE_CONSTELLATION, offset=offset, peaks=peaks
    )


def test_the_scheduler_prefers_a_unit_that_already_has_a_candidate_cell():
    ledger = jumpscan.JumpLedger()
    roster_keys = [("enemy", index) for index in range(4)]
    ledger.record(_jump(("enemy", 0), (2, 2), (0.0, 0.0), ()))
    ledger.hint(("enemy", 2), [(3, 2)])

    assert jumpscan.next_target(ledger, roster_keys) == ("enemy", 2)


def test_the_scheduler_falls_back_to_roster_order_and_stops_at_the_end():
    ledger = jumpscan.JumpLedger()
    roster_keys = [("enemy", index) for index in range(3)]

    assert jumpscan.next_target(ledger, roster_keys) == ("enemy", 0)
    for key in roster_keys:
        ledger.record(_jump(key, (0, 0), (0.0, 0.0), ()))
    assert jumpscan.next_target(ledger, roster_keys) is None


def test_a_failure_sends_the_unit_to_the_back_of_the_queue():
    """開機保護：換一台就換一個落點，原地重試同一台是把同一個死局再跑一次。"""
    ledger = jumpscan.JumpLedger()
    roster_keys = [("enemy", 0), ("enemy", 1)]
    ledger.fail(("enemy", 0))

    assert jumpscan.next_target(ledger, roster_keys) == ("enemy", 1)

    ledger.fail(("enemy", 1))
    assert jumpscan.next_target(ledger, roster_keys) == ("enemy", 0)


def test_two_failures_retire_a_unit_from_the_schedule():
    ledger = jumpscan.JumpLedger()
    roster_keys = [("enemy", 0), ("enemy", 1)]
    for _ in range(2):
        ledger.fail(("enemy", 0))

    assert jumpscan.next_target(ledger, roster_keys) == ("enemy", 1)

    for _ in range(2):
        ledger.fail(("enemy", 1))
    assert jumpscan.next_target(ledger, roster_keys) is None


def test_a_co_sighted_pair_that_agrees_raises_nothing():
    ledger = jumpscan.JumpLedger()
    # A 的窗鏡位 (0,0)：A 在世界格 (11,5)＝螢幕 (1150,550)，B 在 (12,5)＝(1250,550)。
    ledger.record(_jump(("enemy", 0), (11, 5), (0.0, 0.0), ((1150.0, 550.0), (1250.0, 550.0))))
    ledger.record(_jump(("enemy", 1), (12, 5), (100.0, 0.0), ((1150.0, 550.0), (1050.0, 550.0))))

    assert jumpscan.audit(ledger, GRID) == []


def test_a_pair_whose_world_cells_disagree_with_what_the_window_saw_is_flagged():
    ledger = jumpscan.JumpLedger()
    ledger.record(_jump(("enemy", 0), (11, 5), (0.0, 0.0), ((1150.0, 550.0),)))
    ledger.record(_jump(("enemy", 1), (12, 5), (100.0, 0.0), ((1150.0, 550.0),)))

    flags = jumpscan.audit(ledger, GRID)

    assert {(flag.seen_from, flag.about) for flag in flags} == {
        (("enemy", 0), ("enemy", 1)),
        (("enemy", 1), ("enemy", 0)),
    }


def test_a_unit_projected_outside_the_window_is_not_a_co_sighting():
    ledger = jumpscan.JumpLedger()
    ledger.record(_jump(("enemy", 0), (11, 5), (0.0, 0.0), ((1150.0, 550.0),)))
    ledger.record(_jump(("enemy", 1), (400, 5), (0.0, 0.0), ((1150.0, 550.0),)))

    assert jumpscan.audit(ledger, GRID) == []


def test_the_blank_cell_avoids_both_the_peaks_and_the_red_range():
    frame = np.zeros((1080, 2340, 3), np.uint8)
    frame[:, :] = (60, 60, 60)
    # 整個左半塗紅（攻擊範圍），右半只有一個峰。
    frame[:, :1200] = (30, 30, 200)
    peaks = [(1400.0, 550.0)]

    tap = jumpscan.blank_cell_tap(frame, GRID, (0.0, 0.0), peaks)

    assert tap is not None
    assert tap[0] > 1200
    assert abs(tap[0] - 1400) > GRID.col_pitch


def test_no_blank_cell_when_the_whole_window_is_red():
    frame = np.zeros((1080, 2340, 3), np.uint8)
    frame[:, :] = (30, 30, 200)

    assert jumpscan.blank_cell_tap(frame, GRID, (0.0, 0.0), []) is None


def test_the_blank_cell_never_lands_under_the_ui_that_covers_the_map():
    """「離畫面中心最遠」天生指向四角，而四角全是 UI：0806 實機挑到 (2238,1011)，
    壓在右下「單位列表」鈕上（被 device 的 weapon_dial 危險帶攔下才發現）。"""
    frame = np.zeros((1080, 2340, 3), np.uint8)
    frame[:, :] = (60, 60, 60)

    tap = jumpscan.blank_cell_tap(frame, GRID, (0.0, 0.0), [])

    assert tap is not None
    assert not jumpscan.in_ui_zone(tap)


def test_the_unit_list_button_and_the_top_bar_are_inside_the_mask():
    assert jumpscan.in_ui_zone((2238.0, 1011.0))
    assert jumpscan.in_ui_zone((1170.0, 60.0))
    assert jumpscan.in_ui_zone((1900.0, 60.0))
    assert jumpscan.in_ui_zone((300.0, 200.0))
    assert jumpscan.in_ui_zone((400.0, 1000.0))
    assert not jumpscan.in_ui_zone((1170.0, 540.0))


def test_no_blank_cell_when_the_mask_swallows_every_survivor():
    """遮罩之外全紅、遮罩之內乾淨——挑不出來就是挑不出來，不准退回遮罩裡。"""
    frame = np.zeros((1080, 2340, 3), np.uint8)
    frame[:, :] = (30, 30, 200)
    for x, y, w, h in jumpscan.UI_EXCLUSION_ZONES:
        frame[y : y + h, x : x + w] = (60, 60, 60)

    assert jumpscan.blank_cell_tap(frame, GRID, (0.0, 0.0), []) is None


def test_the_report_keeps_roster_order_and_marks_the_unresolved():
    ledger = jumpscan.JumpLedger()
    ledger.record(_jump(("ally", 0), (3, 4), (0.0, 0.0), ()))

    report = jumpscan.ledger_report(ledger, [("ally", 0), ("ally", 1)])

    assert report[0]["cell"] == [3, 4]
    assert report[1]["cell"] is None
    assert report[1]["source"] == jumpscan.UNRESOLVED
