"""名冊跳轉掃描：詳情頁讀值（兩種佈局）、列表格座標、指定標示、march 計格、接力帳。"""

from __future__ import annotations

import numpy as np

from ggge_ai.battle import vision
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


# ---------- 路徑 B'：march 順路結帳（點到單位就地認人） ----------

# 真值檔 assets/stage_truth/uc_hard_1.json 的敵方數值：頭目三台各自唯一，雜魚整批撞名。
TRUTH_HP_EN = {
    ("enemy", 0): (83811, 513),
    ("enemy", 1): (167817, 594),
    ("enemy", 2): (109440, 750),
    ("enemy", 3): (29265, 424),
    ("enemy", 4): (29265, 424),
    ("enemy", 5): (61506, 510),
    ("enemy", 6): (61506, 510),
}


def test_a_boss_number_names_exactly_one_unit():
    match = jumpscan.roster_lookup((167817, 594), TRUTH_HP_EN, [("enemy", 1)])

    assert match == jumpscan.MeetMatch(("enemy", 1), jumpscan.MEET_UNIQUE)


def test_a_number_the_whole_squad_shares_names_nobody():
    """同型量產機整批 29265/424：撞名就是撞名，身分不猜。"""
    match = jumpscan.roster_lookup((29265, 424), TRUTH_HP_EN, TRUTH_HP_EN)

    assert match.key is None and match.reason == jumpscan.MEET_COLLISION


def test_a_unique_number_whose_unit_is_not_solved_yet_is_no_anchor():
    match = jumpscan.roster_lookup((83811, 513), TRUTH_HP_EN, [("enemy", 1)])

    assert match == jumpscan.MeetMatch(("enemy", 0), jumpscan.MEET_UNSOLVED)


def test_a_half_read_summary_is_not_a_lookup_key():
    """摘要窗只讀到一半（字模吐 None）就不反查——湊數的鍵會對到別台。"""
    match = jumpscan.roster_lookup((83811, None), TRUTH_HP_EN, TRUTH_HP_EN)

    assert match.key is None and match.reason == jumpscan.MEET_NO_READ


def test_numbers_that_belong_to_nobody_are_not_forced_onto_the_nearest_unit():
    match = jumpscan.roster_lookup((1, 2), TRUTH_HP_EN, TRUTH_HP_EN)

    assert match.key is None and match.reason == jumpscan.MEET_NO_MATCH


def test_only_three_of_this_stage_s_enemies_can_be_named_by_their_numbers():
    """本關的反查上限：18 台敵方裡只有三台頭目的 HP/EN 組合唯一，其餘整批撞名。"""
    named = [
        key
        for key, values in TRUTH_HP_EN.items()
        if jumpscan.roster_lookup(values, TRUTH_HP_EN, TRUTH_HP_EN).reason
        == jumpscan.MEET_UNIQUE
    ]

    assert named == [("enemy", 0), ("enemy", 1), ("enemy", 2)]


def test_the_two_factions_dock_their_summary_on_opposite_sides():
    """摘要列分側：敵方在左上、我方在右上，兩張實幀各驗一次。

    兩側各有自己的區域（我方＝左側版面整體右移 `SUMMARY_RIGHT_DOCK_SHIFT`），**不共用**：
    共用就等於在我方畫面上拿左上那塊當數值讀，讀到的是別的東西。反向也要拒讀，否則
    「哪一側有卡」這個訊號本身就沒了。
    """
    enemy = load("panels/enemy_summary_designation_20260806")
    ally = load("panels/ally_summary_unit_move_20260806")

    theirs = vision.read_enemy_summary(enemy)
    ours = vision.read_ally_summary(ally)

    assert (theirs.hp, theirs.en) == (29265, 424)
    assert (ours.hp, ours.en) == (38311, 148)
    assert vision.read_ally_summary(enemy) is None
    assert vision.read_enemy_summary(ally) is None


def test_the_seed_candidates_never_leave_the_region_the_marker_can_be_found_in():
    """填色的 learn／find 只看 MAP_REGION——區外種下去的標記哪一幀都找不到。

    0806 run 20260806-173300：北向 frontier 專挑 row 0/1（格心 y≈90-203，在 MAP_REGION
    的 y=250 之上），36 筆 no_seed 全部出在這裡。
    """
    frame = np.zeros((1080, 2340, 3), np.uint8)
    top_row = (900.0, 150.0)
    inside = (900.0, 500.0)

    points = jumpscan.clean_points(
        frame, [top_row, inside], [], keep_out=10.0, red_half=RED_HALF, inside=board.MAP_REGION
    )

    assert points == [inside]


def test_the_nearest_hints_are_the_ones_worth_asking():
    """hint 只決定去哪問（近的先問），身分與位置都不由它回答。"""
    hints = [(5, 5), (9, 9), (6, 4), (3, 3)]

    assert jumpscan.probe_cells(hints, (5, 5), limit=2) == ((6, 4), (3, 3))


def test_a_pan_whose_travel_was_never_booked_blocks_the_border_reading():
    """推了兩把卻只記到一把的位移：帳是缺的，見界也不准出。"""
    audit = jumpscan.audit_march(_legs((2, 4)), pans=2)

    assert not audit.ok and audit.reason == jumpscan.AUDIT_UNACCOUNTED_PAN


def test_a_border_reached_without_moving_at_all_is_a_fake_border():
    """0806 run 20260806-173300 的 enemy#3：假北界＋travel=0 互鎖成自洽的錯答案。"""
    audit = jumpscan.audit_march(_legs((3, 3), (4, 4)), pans=2)

    assert not audit.ok and audit.reason == jumpscan.AUDIT_NO_TRAVEL


def test_a_clean_march_passes_its_own_audit():
    audit = jumpscan.audit_march(_legs((2, 4), (1, 3)), pans=2)

    assert audit.ok and (audit.travel, audit.pans) == (4, 2)


def test_one_suspect_leg_downgrades_the_whole_axis():
    """含存疑的腿就不出帳——寧可 unresolved，不要差一格的毒帳。"""
    audit = jumpscan.audit_march(_legs((2, 4), (1, 3)), pans=2, suspect=1)

    assert not audit.ok and audit.reason == jumpscan.AUDIT_SUSPECT_LEG


def test_a_leg_that_moved_nothing_like_the_stroke_is_suspect():
    """名義行程 260px／格距 130 ＝ 2 格；標記只走 1 格就是對不上。"""
    assert jumpscan.leg_suspect(1, stroke=260.0, pitch=130.0)
    assert not jumpscan.leg_suspect(2, stroke=260.0, pitch=130.0)
    # 半格以內的誤差是 snap 的正常抖動，不罰。
    assert not jumpscan.leg_suspect(2, stroke=195.0, pitch=130.0)
    # 格距讀不出來就不表態，不冤枉。
    assert not jumpscan.leg_suspect(5, stroke=260.0, pitch=0.0)


def test_the_frame_gap_between_the_named_unit_and_the_target_is_the_world_gap():
    """認出來的那台在世界 (12,3)、這一幀的 (7,2)，目標在同一幀的 (5,5)：兩軸同時出帳。"""
    assert jumpscan.meet_cell((12, 3), (7, 2), (5, 5)) == (10, 6)


# ---------- （已下架）指派驗證版的順路結帳 ----------

MEET_WINDOW = (0, 0, 15, 9)


def _meet_scene(target_world, marker_frame, target_frame, worlds):
    """造一個鏡位：里程計（標記相對目標的世界格差）＋各世界格在這一幀的格。"""
    odometer = jumpscan.MarkerOdometer.seeded(marker_frame, target_frame)
    shift = (target_world[0] - target_frame[0], target_world[1] - target_frame[1])
    frames = [(world[0] - shift[0], world[1] - shift[1]) for world in worlds]
    return odometer, frames


def test_a_unique_assignment_settles_both_axes_without_reaching_the_border():
    """里程計把平移鎖死，剩下的只有配對；撐得住的假設唯一就結帳。"""
    resolved = [(12, 3), (14, 6), (11, 8)]
    odometer, hints = _meet_scene((9, 4), (7, 5), (5, 5), resolved)

    fix = jumpscan.march_meet(hints, (7, 5), odometer, resolved, window=MEET_WINDOW)

    assert fix.cell == (9, 4)
    assert (fix.reason, fix.hypotheses) == (jumpscan.MEET_OK, 1)
    assert fix.hint in hints


def test_two_surviving_assignments_settle_nothing():
    """等距排開的隊形（同型量產機列陣）對兩種指派一樣自洽：拒收，繼續推。"""
    resolved = [(10, 4), (12, 4), (14, 4)]
    odometer, hints = _meet_scene((9, 6), (6, 6), (5, 6), resolved)

    fix = jumpscan.march_meet(hints, (6, 6), odometer, resolved, window=MEET_WINDOW)

    assert fix.cell is None and fix.reason == jumpscan.MEET_AMBIGUOUS
    assert fix.hypotheses > 1


def test_a_hint_one_cell_off_does_not_kill_the_right_assignment():
    """hint 是啟發式候選，圖示中心壓在格線上是常態——差一格仍算命中，否則對的假設先死。

    抖一格的代價是它同時生出一個整體平移一格的對手假設，於是這一幀不結帳（保守）：
    容忍度換來的是「不會冤枉對的那個」，不是「照樣收得下去」。
    """
    resolved = [(12, 3), (14, 6), (11, 8)]
    odometer, hints = _meet_scene((9, 4), (7, 5), (5, 5), resolved)
    nudged = [hints[0], (hints[1][0] + 1, hints[1][1]), (hints[2][0], hints[2][1] + 1)]

    strict = jumpscan.march_meet(
        nudged, (7, 5), odometer, resolved, window=MEET_WINDOW, tolerance=0
    )
    lenient = jumpscan.march_meet(nudged, (7, 5), odometer, resolved, window=MEET_WINDOW)

    assert strict.reason == jumpscan.MEET_NO_HYPOTHESIS
    assert lenient.reason == jumpscan.MEET_AMBIGUOUS and lenient.hypotheses > 1


def test_a_missing_unit_is_tolerated_once_but_not_twice():
    """圖示被地形蓋掉一台就漏檢一台，容忍；漏到第二台就不是同一個盤面了。"""
    resolved = [(12, 3), (14, 6), (11, 8)]
    odometer, hints = _meet_scene((9, 4), (7, 5), (5, 5), resolved)

    one_missing = jumpscan.march_meet(hints[:2], (7, 5), odometer, resolved, window=MEET_WINDOW)
    two_missing = jumpscan.march_meet(hints[:1], (7, 5), odometer, resolved, window=MEET_WINDOW)

    assert one_missing.cell == (9, 4)
    assert two_missing.cell is None


def test_hints_that_line_up_with_nothing_settle_nothing():
    resolved = [(12, 3), (14, 6), (11, 8)]
    odometer, _ = _meet_scene((9, 4), (7, 5), (5, 5), resolved)

    fix = jumpscan.march_meet([(0, 0)], (7, 5), odometer, resolved, window=MEET_WINDOW)

    assert fix.cell is None and fix.reason == jumpscan.MEET_NO_HYPOTHESIS


def test_the_seed_unit_has_nothing_to_meet():
    """帳面空的時候（第一台）沒有任何已解單位可撞，直接推到界。"""
    odometer = jumpscan.MarkerOdometer.seeded((7, 5), (5, 5))

    fix = jumpscan.march_meet([(3, 3)], (7, 5), odometer, [], window=MEET_WINDOW)

    assert fix.cell is None and fix.reason == jumpscan.MEET_NO_LEDGER


def test_the_odometer_books_both_axes_when_reseeding_drifts_sideways():
    """西推時 y 名義不變，但重種挑的前緣格常常換一列——兩軸都要入帳才不會斜漂。"""
    odometer = jumpscan.MarkerOdometer.seeded((7, 5), (5, 5))
    odometer = odometer.reseeded((7, 5), (2, 7))

    assert odometer.offset == (-3, 2)
    assert odometer.target_frame((9, 3)) == (12, 1)
    assert odometer.delta((9, 3), (9, 3)) == (-3, 2)


def test_a_reseed_that_drifts_still_names_the_same_world_cell():
    """同一個盤面，換了兩次標記（各差一列）之後結帳的答案必須不變。"""
    resolved = [(12, 3), (14, 6), (11, 8)]
    odometer, hints = _meet_scene((9, 4), (7, 5), (5, 5), resolved)
    drifted = odometer.reseeded((7, 5), (4, 8))

    fix = jumpscan.march_meet(hints, (4, 8), drifted, resolved, window=MEET_WINDOW)

    assert fix.cell == (9, 4) and fix.reason == jumpscan.MEET_OK


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
