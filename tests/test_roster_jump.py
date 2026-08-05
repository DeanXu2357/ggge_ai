"""名冊跳轉掃描：詳情頁讀值（兩種佈局）、列表格座標、記帳／排程／共現複核。"""

from __future__ import annotations

import numpy as np

from ggge_ai.runtime import board, jumpscan, roster
from ggge_ai.runtime.coverage import WorldGrid
from ggge_ai.runtime.device import check_tap
from tests.fixtures.frames import load

GRID = WorldGrid(phase=(0.0, 0.0), col_pitch=100.0, row_pitch=100.0)
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

    tap = _blank(frame, peaks)

    assert tap is not None
    assert tap[0] > 1200
    assert abs(tap[0] - 1400) > GRID.col_pitch


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


def test_the_report_keeps_roster_order_and_marks_the_unresolved():
    ledger = jumpscan.JumpLedger()
    ledger.record(_jump(("ally", 0), (3, 4), (0.0, 0.0), ()))

    report = jumpscan.ledger_report(ledger, [("ally", 0), ("ally", 1)])

    assert report[0]["cell"] == [3, 4]
    assert report[1]["cell"] is None
    assert report[1]["source"] == jumpscan.UNRESOLVED


def _pattern(cells, window=(-8, -4, 8, 4)):
    return jumpscan.Pattern(tuple(sorted(cells)), window)


def test_two_windows_of_the_same_cluster_give_the_grid_delta_between_their_targets():
    """b 是「站在 a 的 (2,0) 那一台上」看同一叢，所以 b 的目標在 a 的座標系就是 (2,0)。"""
    scene = {(0, 0), (2, 0), (1, 1)}
    a = _pattern(scene)
    b = _pattern({(cell[0] - 2, cell[1]) for cell in scene})

    found = jumpscan.match_patterns(a, b)

    assert found.delta == (2, 0)
    assert found.reason == jumpscan.MATCH_OK
    assert found.overlap == 3


def test_a_uniform_row_has_more_than_one_feasible_shift_and_is_refused():
    """整列等距的單位是規則陣列的別名：窗一裁，平移 0／±1 都自洽。寧可漏認不可錯認。"""
    row = _pattern({(-2, 0), (-1, 0), (0, 0), (1, 0), (2, 0)}, window=(-2, -1, 2, 1))

    found = jumpscan.match_patterns(row, row, margin=0)

    assert found.delta is None
    assert found.reason == jumpscan.MATCH_AMBIGUOUS


def test_two_windows_that_share_nothing_are_no_match():
    a = _pattern({(0, 0), (1, 0), (2, 2)})
    b = _pattern({(0, 0), (5, 3), (-4, -3)})

    assert jumpscan.match_patterns(a, b).reason == jumpscan.MATCH_NO_MATCH


def test_a_window_with_only_its_own_target_cannot_anchor_anything():
    lonely = _pattern({(0, 0)})

    assert jumpscan.match_patterns(lonely, lonely).reason == jumpscan.MATCH_FEW_PEAKS


def _anchor(key, cell):
    return [jumpscan.AxisAnchor(key, 0, cell[0]), jumpscan.AxisAnchor(key, 1, cell[1])]


def test_the_chain_propagates_world_cells_from_a_single_anchor():
    edges = [
        jumpscan.ChainEdge(("ally", 0), ("ally", 1), (1, 0), 3),
        jumpscan.ChainEdge(("ally", 1), ("enemy", 0), (2, 3), 4),
    ]

    solution = jumpscan.propagate(edges, _anchor(("ally", 0), (5, 5)))

    assert solution.anchored(("ally", 0))
    assert solution.world(("ally", 1)) == (6, 5)
    assert solution.world(("enemy", 0)) == (8, 8)
    assert solution.conflicts == ()


def test_the_chain_walks_edges_backwards_too():
    edges = [jumpscan.ChainEdge(("ally", 0), ("ally", 1), (1, 0), 3)]

    solution = jumpscan.propagate(edges, _anchor(("ally", 1), (4, 4)))

    assert solution.world(("ally", 0)) == (3, 4)


def test_a_cycle_that_does_not_close_records_a_conflict_and_overwrites_nothing():
    """同一台由兩條路徑到達的格不一致——我們不知道哪一條錯，所以兩邊都不動。"""
    edges = [
        jumpscan.ChainEdge(("ally", 0), ("ally", 1), (1, 0), 3),
        jumpscan.ChainEdge(("ally", 1), ("ally", 2), (1, 0), 3),
        jumpscan.ChainEdge(("ally", 0), ("ally", 2), (5, 0), 3),
    ]

    solution = jumpscan.propagate(edges, _anchor(("ally", 0), (0, 0)))

    assert len(solution.conflicts) == 1
    conflict = solution.conflicts[0]
    assert conflict.key == ("ally", 2)
    assert {conflict.known, conflict.saw} == {(2, 0), (5, 0)}
    assert solution.cells[("ally", 2)] == conflict.known


def test_two_axis_anchors_that_disagree_are_a_conflict_not_a_silent_overwrite():
    edges = [jumpscan.ChainEdge(("ally", 0), ("ally", 1), (1, 0), 3)]

    solution = jumpscan.propagate(
        edges, [*_anchor(("ally", 0), (0, 0)), *_anchor(("ally", 1), (9, 9))]
    )

    assert [(c.key, c.axis) for c in solution.axis_conflicts] == [(("ally", 1), 0), (("ally", 1), 1)]
    # 先到的說了算，後到的只記帳：我們不知道哪一個界讀錯了。
    assert solution.world(("ally", 1)) == (1, 0)


def test_zero_anchors_still_produce_a_relative_map_marked_unanchored():
    """錨可以下一輪再補，鏈的形狀本身就是成果——不 Halt，交相對格出去。"""
    edges = [jumpscan.ChainEdge(("ally", 0), ("ally", 1), (2, 1), 3)]

    solution = jumpscan.propagate(edges)

    assert not solution.any_anchor
    assert solution.world(("ally", 1)) == (None, None)
    assert solution.cells[("ally", 1)][0] - solution.cells[("ally", 0)][0] == 2
    assert solution.cells[("ally", 1)][1] - solution.cells[("ally", 0)][1] == 1


def test_one_axis_from_one_window_anchors_that_axis_for_the_whole_component():
    """單軸也是硬證據：西界只給 x，整個元件的 x 就定了，y 仍然是 None。"""
    edges = [
        jumpscan.ChainEdge(("ally", 0), ("ally", 1), (2, 1), 3),
        jumpscan.ChainEdge(("ally", 1), ("ally", 2), (1, 1), 3),
    ]

    solution = jumpscan.propagate(edges, [jumpscan.AxisAnchor(("ally", 1), 0, 10)])

    assert solution.axes(("ally", 2)) == ("x",)
    assert solution.world(("ally", 0)) == (8, None)
    assert solution.world(("ally", 2)) == (11, None)
    assert not solution.anchored(("ally", 2))
    assert solution.any_anchor


def test_the_two_axes_may_come_from_different_windows():
    edges = [jumpscan.ChainEdge(("ally", 0), ("ally", 1), (2, 1), 3)]

    solution = jumpscan.propagate(
        edges,
        [jumpscan.AxisAnchor(("ally", 0), 0, 5), jumpscan.AxisAnchor(("ally", 1), 1, 7)],
    )

    assert solution.axes(("ally", 0)) == ("x", "y")
    assert solution.world(("ally", 0)) == (5, 6)
    assert solution.world(("ally", 1)) == (7, 7)


def test_an_anchor_only_moves_its_own_component():
    edges = [
        jumpscan.ChainEdge(("ally", 0), ("ally", 1), (1, 0), 3),
        jumpscan.ChainEdge(("enemy", 0), ("enemy", 1), (1, 0), 3),
    ]

    solution = jumpscan.propagate(edges, _anchor(("ally", 0), (4, 4)))

    assert solution.components[("ally", 0)] != solution.components[("enemy", 0)]
    assert solution.world(("ally", 1)) == (5, 4)
    assert solution.world(("enemy", 1)) == (None, None)


def test_a_window_that_never_linked_to_anything_is_reported_unresolved():
    """孤立節點的相對格只對自己成立，寫出來會被當成座標讀——所以不寫。"""
    ledger = jumpscan.JumpLedger()
    ledger.patterns[("ally", 0)] = _pattern({(0, 0), (1, 0)})

    report = jumpscan.ledger_report(ledger, [("ally", 0), ("ally", 1)])

    assert report[0]["source"] == jumpscan.UNRESOLVED
    assert report[0]["component"] is None
    assert report[0]["relative_cell"] is None
    assert report[1]["cell"] is None
    assert report[1]["source"] == jumpscan.UNRESOLVED


def test_the_report_keeps_the_absolute_source_for_anchors_and_marks_the_rest_chain():
    ledger = jumpscan.JumpLedger()
    ledger.record(_jump(("ally", 0), (3, 4), (0.0, 0.0), ()))
    ledger.patterns[("ally", 0)] = _pattern({(0, 0), (1, 0)})
    ledger.patterns[("ally", 1)] = _pattern({(0, 0), (-1, 0)})
    ledger.edges.append(jumpscan.ChainEdge(("ally", 0), ("ally", 1), (1, 0), 2))

    report = jumpscan.ledger_report(ledger, [("ally", 0), ("ally", 1)])

    assert report[0]["source"] == jumpscan.SOURCE_CONSTELLATION
    assert report[0]["cell"] == [3, 4]
    assert report[1]["source"] == jumpscan.SOURCE_CHAIN
    assert report[1]["cell"] == [4, 4]
    assert report[1]["anchored_axes"] == ["x", "y"]
    assert report[0]["component"] == report[1]["component"]


def test_a_component_anchored_on_one_axis_reports_that_axis_and_no_absolute_cell():
    ledger = jumpscan.JumpLedger()
    ledger.patterns[("ally", 0)] = _pattern({(0, 0), (1, 0)})
    ledger.patterns[("ally", 1)] = _pattern({(0, 0), (-1, 0)})
    ledger.edges.append(jumpscan.ChainEdge(("ally", 0), ("ally", 1), (1, 0), 3))
    ledger.anchor_axis(("ally", 0), 0, 12)

    report = jumpscan.ledger_report(ledger, [("ally", 0), ("ally", 1)])

    assert report[1]["anchored_axes"] == ["x"]
    assert report[1]["cell"] is None
    assert report[1]["relative_cell"] == [1, 0]
    assert report[1]["source"] == jumpscan.SOURCE_CHAIN


def test_linking_a_window_records_the_pattern_and_grows_the_edges():
    ledger = jumpscan.JumpLedger()
    scene = {(0, 0), (2, 0), (1, 1)}
    ledger.link(("ally", 0), _pattern(scene))
    matches = ledger.link(("ally", 1), _pattern({(c[0] - 2, c[1]) for c in scene}))

    assert [found.delta for _, found in matches] == [(2, 0)]
    assert ledger.edges[0].frm == ("ally", 0)
    assert ledger.edges[0].to == ("ally", 1)
    assert ledger.resolved(("ally", 1))


def test_an_isolated_window_still_reports_the_axis_it_measured():
    """接不上鏈不等於什麼都不知道：量到西界就是量到了，那一軸照樣說出來。"""
    ledger = jumpscan.JumpLedger()
    ledger.patterns[("ally", 0)] = _pattern({(0, 0), (1, 0)})
    ledger.anchor_axis(("ally", 0), 0, 7)

    report = jumpscan.ledger_report(ledger, [("ally", 0)])

    assert report[0]["source"] == jumpscan.UNRESOLVED
    assert report[0]["component"] is None
    assert report[0]["anchored_axes"] == ["x"]
    assert report[0]["cell"] is None


def _chain(*edges):
    return [jumpscan.ChainEdge(frm, to, delta, 5) for frm, to, delta in edges]


LINE = _chain(
    (("ally", 0), ("ally", 1), (0, -2)),
    (("ally", 1), ("ally", 2), (0, -3)),
    (("ally", 2), ("ally", 3), (1, 5)),
)


def test_the_frontier_for_a_missing_axis_is_the_unit_furthest_along_it():
    """缺 y 就挑相對 row 最小的那台——最靠北，跳過去最有機會把北界拉進畫面。"""
    solution = jumpscan.propagate(LINE)
    component = solution.components[("ally", 0)]

    assert jumpscan.axis_frontier(solution, component, 1) == (("ally", 2), ("ally", 1))
    assert jumpscan.axis_frontier(solution, component, 0)[0] == ("ally", 0)


def test_a_tie_on_the_frontier_goes_to_the_earlier_roster_entry():
    edges = _chain(
        (("enemy", 5), ("ally", 3), (0, 0)),
        (("enemy", 5), ("enemy", 1), (0, 4)),
    )
    solution = jumpscan.propagate(edges)
    component = solution.components[("enemy", 5)]
    roster = [("ally", 3), ("enemy", 5), ("enemy", 1)]

    assert jumpscan.axis_frontier(solution, component, 1, roster=roster, limit=1) == (("ally", 3),)


def test_the_frontier_never_offers_more_than_the_retry_budget():
    solution = jumpscan.propagate(LINE)
    component = solution.components[("ally", 0)]

    assert len(jumpscan.axis_frontier(solution, component, 1)) == jumpscan.ANCHOR_ATTEMPTS
    assert len(jumpscan.axis_frontier(solution, component, 1, limit=1)) == 1


def test_only_the_axis_that_is_still_missing_is_worth_a_second_jump():
    solution = jumpscan.propagate(LINE, [jumpscan.AxisAnchor(("ally", 0), 0, 4)])
    component = solution.components[("ally", 0)]

    assert jumpscan.needy_axes(solution) == [(component, 1)]


def test_a_component_too_small_to_be_worth_the_trip_is_not_offered():
    """size<3 的元件補到了也只定得了自己那幾台，不值一趟完整的選單→跳轉→解除。"""
    solution = jumpscan.propagate(_chain((("ally", 0), ("ally", 1), (1, 1))))

    assert jumpscan.needy_axes(solution) == []
    assert len(jumpscan.needy_axes(solution, min_size=2)) == 2


def test_an_axis_that_stays_unreadable_leaves_the_ledger_partially_anchored():
    """補跳兩台都讀不到北界就放棄那一軸——帳面維持部分錨定，不是失敗。"""
    ledger = jumpscan.JumpLedger()
    for index, cells in enumerate(({(0, 0), (1, 0)}, {(0, 0), (-1, 0)}, {(0, 0), (2, 0)})):
        ledger.patterns[("ally", index)] = _pattern(cells)
    ledger.edges.extend(LINE[:2])
    ledger.anchor_axis(("ally", 0), 0, 9)

    report = jumpscan.ledger_report(ledger, [("ally", 0), ("ally", 1), ("ally", 2)])

    assert [row["anchored_axes"] for row in report] == [["x"], ["x"], ["x"]]
    assert [row["cell"] for row in report] == [None, None, None]
    assert [row["relative_cell"] for row in report] == [[0, 0], [0, -2], [0, -5]]
