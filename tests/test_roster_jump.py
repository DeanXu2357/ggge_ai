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



# ---------- 敵方的目標端：攻擊範圍紅菱形 ----------


def _scene(cells, pitch=100.0):
    return {cell: (1170.0 + pitch * cell[0], 540.0 + pitch * cell[1]) for cell in cells}


def _red_frame(cells, scene, half=30):
    frame = np.full((1080, 2340, 3), 60, np.uint8)
    for cell in cells:
        x, y = scene[cell]
        frame[int(y - half) : int(y + half), int(x - half) : int(x + half)] = (30, 30, 200)
    return frame


def _ring(centre, reach):
    return {
        (x, y)
        for x in range(centre[0] - reach, centre[0] + reach + 1)
        for y in range(centre[1] - reach, centre[1] + reach + 1)
        if abs(x - centre[0]) + abs(y - centre[1]) <= reach
    }


def test_the_attack_range_diamond_names_the_enemy_cell():
    """0806 run 20260806-121910 的 36 張敵方落點幀：紅範圍是整片實心菱形，最小包覆
    半徑的中心每一張都唯一，而且與「跳轉把目標帶到畫面中心」完全一致（36/36）。"""
    scene = _scene({(x, y) for x in range(-4, 5) for y in range(-4, 5)})
    marks = _ring((0, 0), 3)

    assert jumpscan.attack_centre(marks) == (0, 0)
    assert jumpscan.attack_cells(_red_frame(marks, scene), scene, half=20.0) == tuple(
        sorted(marks)
    )


def test_units_standing_in_the_range_punch_holes_that_do_not_move_the_centre():
    """紅格會被單位圖示蓋掉幾格（目標自己那一格幾乎一定被蓋）——包覆半徑不受影響。"""
    marks = _ring((2, 3), 4) - {(2, 3), (3, 3), (1, 3), (2, 2)}

    assert jumpscan.attack_centre(marks) == (2, 3)


def test_the_ui_cards_over_the_map_are_not_attack_range():
    """左上單位卡的 HP 紅條就疊在地圖上層，實幀重放時它每次都吐兩三格假紅。"""
    scene = _scene({(0, 0), (1, 0)})
    scene[(-9, -4)] = (300.0, 200.0)
    frame = _red_frame({(0, 0), (1, 0), (-9, -4)}, scene)

    assert jumpscan.attack_cells(frame, scene, half=20.0) == ((0, 0), (1, 0))


def test_a_shifted_centre_needs_a_bigger_diamond_and_loses():
    """判準是最小包覆半徑：往東挪一格就得把半徑加一才包得住西邊那幾格。"""
    marks = _ring((5, 5), 2)
    reach = {cell: max(abs(cell[0] - m[0]) + abs(cell[1] - m[1]) for m in marks)
             for cell in ((5, 5), (6, 5), (5, 6))}

    assert reach[(5, 5)] == 2
    assert reach[(6, 5)] == reach[(5, 6)] == 3
    assert jumpscan.attack_centre(marks) == (5, 5)


def test_no_red_cells_at_all_is_not_a_fit():
    assert jumpscan.attack_centre([]) is None


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


def test_two_confirmed_cells_lock_the_window_onto_the_world():
    """窗位＝幀格與已解世界格之間的平移；唯一解才採信，身分完全不參與。"""
    references = [(10, 5), (12, 4), (7, 9)]
    occupied = [(3, 2), (5, 1)]

    fix = jumpscan.window_offset(references, occupied)

    assert fix.delta == (7, 3)
    assert (fix.matched, fix.reason) == (2, jumpscan.MATCH_OK)


def test_one_confirmed_cell_is_not_a_constellation():
    """一格到處都對得上——形狀要兩格才談得上。"""
    fix = jumpscan.window_offset([(10, 5), (12, 4)], [(3, 2)])

    assert fix.delta is None and fix.reason == jumpscan.MATCH_FEW_CELLS


def test_a_regular_lattice_of_units_is_refused_rather_than_guessed():
    """等距排開的隊形對兩個平移一樣自洽：拒收，不猜。"""
    references = [(0, 0), (2, 0), (4, 0)]
    occupied = [(0, 0), (2, 0)]

    fix = jumpscan.window_offset(references, occupied)

    assert fix.delta is None and fix.reason == jumpscan.MATCH_AMBIGUOUS


def test_a_window_whose_units_are_all_unsolved_matches_nothing():
    fix = jumpscan.window_offset([(10, 5), (12, 4)], [(3, 2), (9, 9)])

    assert fix.delta is None and fix.reason == jumpscan.MATCH_NO_MATCH


def test_unsolved_units_in_the_window_do_not_veto_a_match():
    """幀裡本來就有還沒解的單位，它們只是配不到參考，不該否決整個平移。"""
    references = [(10, 5), (12, 4), (11, 7)]
    occupied = [(3, 2), (5, 1), (0, 0)]

    fix = jumpscan.window_offset(references, occupied)

    assert fix.delta == (7, 3) and fix.matched == 2


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
    ledger.anchor(("ally", 1), (4, 4), jumpscan.SOURCE_CONSTELLATION)

    report = jumpscan.ledger_report(ledger, [("ally", 0), ("ally", 1), ("ally", 2)])

    assert [found["cell"] for found in report] == [[3, 4], [4, 4], None]
    assert [found["source"] for found in report] == [
        jumpscan.SOURCE_MARCH,
        jumpscan.SOURCE_CONSTELLATION,
        jumpscan.UNRESOLVED,
    ]


def test_a_moving_camera_shows_up_as_a_whole_screen_change():
    """鏡頭在動＝整片都在變；待機動畫只有幾個百分點。0806 實幀量到的分界是
    同鏡位 0.007-0.04 vs 跳轉途中 0.15-0.37。"""
    quiet = np.full((1080, 2340, 3), 60, np.uint8)
    twitch = quiet.copy()
    twitch[500:540, 1150:1190] = (200, 200, 200)
    moved = np.full((1080, 2340, 3), 200, np.uint8)

    assert jumpscan.changed_fraction(quiet, twitch) < 0.01
    assert jumpscan.changed_fraction(quiet, moved) > 0.9


# ---------- 我方的目標端：移動範圍菱形 ----------


def _diamond(centre, reach, window=None):
    cells = set()
    for x in range(centre[0] - reach, centre[0] + reach + 1):
        for y in range(centre[1] - reach, centre[1] + reach + 1):
            if abs(x - centre[0]) + abs(y - centre[1]) > reach:
                continue
            if window and not (window[0] <= x <= window[2] and window[1] <= y <= window[3]):
                continue
            cells.add((x, y))
    return cells


def test_the_move_range_diamond_names_the_cell_the_unit_stands_on():
    """實幀 assets/screenshots/20260806-013500.png 的形狀：中心那一格自己沒有徽章
    （單位圖示蓋著），一堆格被圖示與地形擋掉，剩下的仍然唯一定出中心。"""
    marks = _diamond((6, 5), 5) - {(6, 5), (5, 5), (7, 5), (6, 4), (4, 3), (8, 6)}

    assert jumpscan.diamond_centre(marks, 5) == (6, 5)


def test_a_mark_beyond_the_move_range_vetoes_that_centre():
    """標記是遊戲自己畫的，畫出來的格不可能超過移動力——多看到一格就否決那個中心。"""
    marks = _diamond((6, 5), 3) | {(6, 12)}

    assert jumpscan.diamond_centre(marks, 3) is None


def test_a_unit_against_the_west_edge_is_fitted_with_the_mobility_prior():
    """貼邊的菱形被截掉半個，硬條件下可行中心不只一個；預測最少沒看到的區域的那個才對
    ——單純取重心會被截斷拉往東邊。"""
    window = (0, 0, 12, 9)
    marks = _diamond((1, 4), 4, window)

    assert sum(cell[0] for cell in marks) / len(marks) > 1.5
    assert jumpscan.diamond_centre(marks, 4, window=window) == (1, 4)


def test_a_shape_that_two_centres_explain_equally_well_is_refused():
    """裁不出唯一解就別猜：兩個中心一樣好的時候回 None，那台等下一輪。"""
    marks = {(5, 5)}

    assert jumpscan.diamond_centre(marks, 2) is None


def test_no_marks_at_all_is_not_a_fit():
    assert jumpscan.diamond_centre([], 4) is None


def test_the_range_marks_take_the_badges_and_leave_the_hud_bars():
    """右側敵方那條 34x64 的藍色 HUD 條與徽章同色，靠長寬比擋掉——放它進來菱形就無解。"""
    frame = np.zeros((1080, 2340, 3), np.uint8)
    badge = (200, 120, 60)
    # 徽章是圓角的，填充率 0.62-0.75；實心方塊在實幀裡不存在，填充率閘也會擋掉。
    frame[400:443, 800:845] = badge
    for x, y in ((800, 400), (833, 400), (800, 431), (833, 431)):
        frame[y : y + 12, x : x + 12] = 0
    frame[400:464, 1600:1634] = badge
    pitch = (128.0, 120.0)

    found = jumpscan.range_marks(frame, pitch)

    assert len(found) == 1
    assert abs(found[0][0] - 822) < 3 and abs(found[0][1] - 421) < 3
