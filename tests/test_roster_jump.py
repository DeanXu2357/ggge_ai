"""名冊跳轉掃描：詳情頁讀值（兩種佈局）、列表格座標、指定標示、march 計格、接力帳。"""

from __future__ import annotations

import numpy as np

from ggge_ai.runtime import board, jumpscan, roster
from ggge_ai.runtime.device import check_tap
from tests.fixtures.frames import load

PITCH = 100.0
KEEP_OUT = jumpscan.PEAK_KEEP_OUT_PITCH * 100.0
RED_HALF = 100.0 / 3.0


def _centres(region=board.UNIT_DENSITY_REGION, pitch=100.0):
    """幀內格心（螢幕像素）。實機由 battle.map_grid 的逐線格網算，這裡用等距造。"""
    x, y, w, h = region
    return [
        (x + pitch / 2 + pitch * col, y + pitch / 2 + pitch * row)
        for col in range(int(w // pitch))
        for row in range(int(h // pitch))
    ]


def _blank(frame, peaks=(), **kw):
    return jumpscan.blank_cell_tap(
        frame, _centres(), peaks, keep_out=KEEP_OUT, red_half=RED_HALF, **kw
    )


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



def test_the_blank_cell_avoids_both_the_peaks_and_the_red_range():
    frame = np.zeros((1080, 2340, 3), np.uint8)
    frame[:, :] = (60, 60, 60)
    # 整個左半塗紅（攻擊範圍），右半只有一個峰。
    frame[:, :1200] = (30, 30, 200)
    peaks = [(1400.0, 550.0)]

    tap = _blank(frame, peaks)

    assert tap is not None
    assert tap[0] > 1200
    assert abs(tap[0] - 1400) > PITCH


def test_no_blank_cell_when_the_whole_window_is_red():
    frame = np.zeros((1080, 2340, 3), np.uint8)
    frame[:, :] = (30, 30, 200)

    assert _blank(frame) is None


def test_the_blank_cell_never_lands_under_the_ui_that_covers_the_map():
    """「離畫面中心最遠」天生指向四角，而四角全是 UI：0806 實機挑到 (2238,1011)，
    壓在右下「單位列表」鈕上（被 device 的 weapon_dial 危險帶攔下才發現）。"""
    frame = np.zeros((1080, 2340, 3), np.uint8)
    frame[:, :] = (60, 60, 60)

    tap = _blank(frame)

    assert tap is not None
    assert not jumpscan.in_ui_zone(tap)


def test_the_blank_cell_also_clears_the_danger_bands_not_just_the_visible_buttons():
    """帶比可見鈕大，遮罩追不上帶的形狀——0806 第五輪挑到 (2199,260)，遮罩讓它過了
    但 `auto_battle_tristate` 帶擋下來。候選要直接問帶（無 intent 視角）。"""
    frame = np.zeros((1080, 2340, 3), np.uint8)
    frame[:, :] = (60, 60, 60)

    tap = _blank(frame)

    assert tap is not None
    check_tap(*tap)


def test_a_candidate_outside_every_mask_is_still_dropped_when_a_band_covers_it():
    frame = np.zeros((1080, 2340, 3), np.uint8)
    frame[:, :] = (60, 60, 60)
    assert _blank(frame, zones=(), blocked=lambda point: False) is not None
    assert _blank(frame, zones=(), blocked=lambda point: True) is None


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

    assert _blank(frame) is None



# ---------- 目標端定位點：指定標示 ----------


def _scene(cells, pitch=100.0):
    return {cell: (1170.0 + pitch * cell[0], 540.0 + pitch * cell[1]) for cell in cells}


def test_the_designation_mark_names_the_target_cell():
    """目標格由「落點幀 vs 乾淨幀的變化」指出來，不是拿密度峰猜的。"""
    clean = np.full((1080, 2340, 3), 60, np.uint8)
    landing = clean.copy()
    landing[520:560, 1250:1290] = (30, 30, 220)

    found = jumpscan.designation_cell(landing, clean, _scene({(0, 0), (1, 0), (0, 1)}), half=20.0)

    assert found == (1, 0)


def test_no_designation_mark_means_no_target_cell():
    clean = np.full((1080, 2340, 3), 60, np.uint8)

    assert jumpscan.designation_cell(clean, clean, _scene({(0, 0), (1, 0)}), half=20.0) is None


def test_a_full_screen_overlay_falls_back_to_the_cell_the_game_centred():
    """我方移動範圍是一整片同色覆蓋，好幾格一起滿版變化——領先差裁不出來時，
    由「系統自己置中的那一格」收尾。"""
    clean = np.full((1080, 2340, 3), 60, np.uint8)
    landing = np.full((1080, 2340, 3), 200, np.uint8)

    found = jumpscan.designation_cell(landing, clean, _scene({(0, 0), (1, 0), (0, 1)}), half=20.0)

    assert found == (0, 0)


def test_the_peaks_only_pick_which_cell_to_ask_never_the_coordinates():
    peaks = [(1170.0, 540.0), (1280.0, 545.0), (1600.0, 900.0), (1180.0, 640.0)]

    order = jumpscan.probe_order(peaks, (1170.0, 540.0), limit=2)

    assert order == ((1180.0, 640.0), (1280.0, 545.0))


# ---------- 路徑 B：march 計格帳 ----------


def _legs(*pairs):
    return [jumpscan.MarchLeg(before, after) for before, after in pairs]


def test_the_march_counts_cells_leg_by_leg_back_to_the_border():
    """每把推鏡讓標記在幀內往回走幾格，累計起來就是鏡頭走了幾格；界那一幀的
    幀格 0 就是世界 0。"""
    legs = _legs((2, 5), (1, 4), (0, 3))

    assert jumpscan.march_origin(legs, border_cell=0) == 9
    assert jumpscan.march_world(3, legs, border_cell=0) == 12


def test_reseeding_needs_no_extra_leg_because_it_happens_inside_one_frame():
    """重種只是換一顆標記當證人，鏡位沒動——下一把的 before 用新標記的格就好。"""
    carried = _legs((2, 5), (5, 8))
    reseeded = _legs((2, 5), (1, 4))

    assert jumpscan.march_world(0, carried, 0) == jumpscan.march_world(0, reseeded, 0)


def test_a_march_that_never_left_the_border_frame_reads_the_cell_straight_off():
    assert jumpscan.march_world(4, [], border_cell=0) == 4


# ---------- 帳：接力回填、排程、互驗 ----------


def test_a_relay_lands_the_moment_its_neighbour_has_coordinates():
    ledger = jumpscan.JumpLedger()
    ledger.identify(("enemy", 0), "sig-a")
    ledger.anchor(("enemy", 0), (10, 5))
    ledger.relay(("enemy", 1), "sig-a", (2, -1))

    report = ledger.settle()

    assert report.filled == (("enemy", 1),)
    assert ledger.cells[("enemy", 1)] == (12, 4)
    assert ledger.sources[("enemy", 1)] == jumpscan.SOURCE_RELAY


def test_pending_relays_are_backfilled_to_a_fixed_point():
    """點開的鄰居當時還沒有座標也照樣記帳：身分是硬的，幀內格差有格線撐。"""
    ledger = jumpscan.JumpLedger()
    ledger.identify(("enemy", 1), "sig-b")
    ledger.identify(("enemy", 2), "sig-c")
    ledger.relay(("enemy", 2), "sig-b", (1, 1))
    ledger.relay(("enemy", 3), "sig-c", (0, 2))

    assert ledger.settle().filled == ()

    ledger.anchor(("enemy", 1), (4, 4))
    report = ledger.settle()

    assert set(report.filled) == {("enemy", 2), ("enemy", 3)}
    assert ledger.cells[("enemy", 3)] == (5, 7)


def test_a_relay_that_disagrees_with_a_known_cell_is_a_conflict_not_an_overwrite():
    ledger = jumpscan.JumpLedger()
    ledger.identify(("enemy", 0), "sig-a")
    ledger.anchor(("enemy", 0), (10, 5))
    ledger.anchor(("enemy", 1), (12, 4), jumpscan.SOURCE_MARCH)
    ledger.relay(("enemy", 1), "sig-a", (3, -1))

    report = ledger.settle()

    assert [(c.key, c.saw) for c in report.conflicts] == [(("enemy", 1), (13, 4))]
    assert ledger.cells[("enemy", 1)] == (12, 4)
    assert ledger.sources[("enemy", 1)] == jumpscan.SOURCE_MARCH


def test_a_relay_whose_identity_was_never_seen_stays_pending_without_crashing():
    ledger = jumpscan.JumpLedger()
    ledger.relay(("enemy", 4), "sig-unknown", (1, 0))

    assert ledger.settle().filled == ()
    assert jumpscan.audit(ledger) == []


def test_the_same_frame_pair_audits_the_final_cells_against_what_the_frame_saw():
    ledger = jumpscan.JumpLedger()
    ledger.identify(("enemy", 0), "sig-a")
    ledger.anchor(("enemy", 0), (10, 5))
    ledger.anchor(("enemy", 1), (12, 4))
    ledger.relay(("enemy", 1), "sig-a", (2, -1))

    assert jumpscan.audit(ledger) == []

    ledger.anchor(("enemy", 1), (12, 6))
    flags = jumpscan.audit(ledger)

    assert [(flag.key, flag.known, flag.saw) for flag in flags] == [
        (("enemy", 1), (12, 6), (12, 4))
    ]


def test_the_first_target_is_just_the_first_roster_entry():
    ledger = jumpscan.JumpLedger()
    keys = [("ally", index) for index in range(3)]

    assert jumpscan.next_target(ledger, keys) == ("ally", 0)


def test_once_something_is_solved_the_scheduler_sticks_to_its_roster_neighbours():
    """同勢力單位在地圖上成群，名冊相鄰大概率地圖相鄰——鄰居入鏡，接力才便宜。"""
    ledger = jumpscan.JumpLedger()
    keys = [("enemy", index) for index in range(6)]
    ledger.anchor(("enemy", 3), (0, 0))

    assert jumpscan.next_target(ledger, keys) == ("enemy", 2)

    ledger.anchor(("enemy", 2), (1, 0))
    assert jumpscan.next_target(ledger, keys) == ("enemy", 1)


def test_two_failures_retire_a_unit_from_the_schedule():
    ledger = jumpscan.JumpLedger()
    keys = [("enemy", 0), ("enemy", 1)]
    for _ in range(2):
        ledger.fail(("enemy", 0))

    assert jumpscan.next_target(ledger, keys) == ("enemy", 1)

    ledger.retire(("enemy", 1))
    assert jumpscan.next_target(ledger, keys) is None


def test_the_report_is_absolute_cells_or_nothing():
    """相對格只對自己成立，寫出去會被當座標讀——所以帳面只有絕對格與 unresolved。"""
    ledger = jumpscan.JumpLedger()
    ledger.anchor(("ally", 0), (3, 4), jumpscan.SOURCE_MARCH)
    ledger.identify(("ally", 0), "sig-a")
    ledger.relay(("ally", 1), "sig-a", (1, 0))
    ledger.settle()

    report = jumpscan.ledger_report(ledger, [("ally", 0), ("ally", 1), ("ally", 2)])

    assert [found["cell"] for found in report] == [[3, 4], [4, 4], None]
    assert [found["source"] for found in report] == [
        jumpscan.SOURCE_MARCH,
        jumpscan.SOURCE_RELAY,
        jumpscan.UNRESOLVED,
    ]
