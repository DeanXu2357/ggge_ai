"""每格點擊清算掃描的離線測試：帳本、規劃器、三分類器與重錨算術。"""

from __future__ import annotations

import math

import numpy as np
import pytest

from ggge_ai.runtime import board, settle, sweep
from ggge_ai.runtime.coverage import WorldGrid
from ggge_ai.runtime.device import DangerBand

GRID = WorldGrid(phase=(0.0, 0.0), col_pitch=100.0, row_pitch=100.0)
REGION = (0, 0, 400, 300)


def NO_SHIFT(before, after):
    """三分類器的位移量測接縫：合成幀上沒有密度峰可量，明說「量不到」。"""
    return None


def ledger(**boundary: int) -> sweep.SweepLedger:
    book = sweep.SweepLedger(grid=GRID)
    book.boundary.update(boundary)
    return book


def test_the_ledger_only_counts_a_cell_once_it_has_been_sentenced():
    book = ledger()

    assert book.verdict((1, 1)) == sweep.UNKNOWN
    assert not book.decided((1, 1))

    book.record((1, 1), sweep.ENEMY, name="sig-a", frame="frames/x.png")

    assert book.decided((1, 1))
    assert book.names[(1, 1)] == "sig-a"


def test_completion_needs_all_four_borders_and_every_in_bounds_cell_sentenced():
    book = ledger(west=0, east=1, north=0, south=0)

    assert not book.complete
    assert book.pending() == ((0, 0), (1, 0))

    book.record((0, 0), sweep.EMPTY)
    assert not book.complete

    book.record((1, 0), sweep.UNSURE, reason="no_feedback")
    assert book.complete


def test_a_border_is_written_once_and_clips_the_cells_outside_it():
    book = sweep.SweepLedger(grid=GRID)
    book.see_border("west", 0.0)
    book.see_border("west", 500.0)

    assert book.boundary["west"] == 0
    assert not book.in_bounds((-1, 3))
    assert book.in_bounds((4, 3))


def test_the_window_plan_walks_the_rows_serpentine_and_skips_sentenced_cells():
    book = ledger()
    book.record((1, 0), sweep.EMPTY)

    plan = sweep.plan_window(book, (0.0, 0.0), region=REGION, holes=(), bands=())

    assert [target.cell for target in plan.taps][:3] == [(0, 0), (2, 0), (3, 0)]
    # 第二列反向走：蛇形不繞回列首
    assert [target.cell for target in plan.taps][3:7] == [(3, 1), (2, 1), (1, 1), (0, 1)]
    assert plan.taps[0].point == (50.0, 50.0)


def test_cells_only_half_inside_the_click_window_are_not_offered():
    book = ledger()

    plan = sweep.plan_window(book, (50.0, 0.0), region=REGION, holes=(), bands=())

    assert min(target.cell[0] for target in plan.taps) == 1


def test_a_danger_band_or_a_hud_hole_defers_the_cell_instead_of_tapping_it():
    book = ledger()
    band = DangerBand("test", (0, 150), (0, 150), intents=())

    plan = sweep.plan_window(book, (0.0, 0.0), region=REGION, holes=((200, 0, 100, 100),),
                             bands=(band,))

    assert (0, 0) in plan.blocked
    assert (2, 0) in plan.blocked
    assert (0, 0) not in [target.cell for target in plan.taps]

    book.defer((0, 0))
    assert book.blocked[(0, 0)] == 1
    assert book.summary()["deferred"] == [[0, 0]]


def test_a_seen_border_becomes_a_provisional_bound_only_where_the_ledger_has_none():
    veil = sweep.provisional_bounds(
        GRID, (0.0, 100.0), {"south": 150.0, "east": 320.0}, {"east"}
    )

    # 終止邊往界內半格：南緣世界 250 的最外一格是第 2 列
    assert veil == {"south": 2}


def test_a_provisional_border_keeps_the_window_plan_off_everything_beyond_it():
    book = ledger()

    plan = sweep.plan_window(
        book,
        (0.0, 0.0),
        region=REGION,
        holes=((0, 100, 100, 100),),
        bands=(),
        candidates={(0, 0)},
        veil={"south": 1},
    )

    assert plan.blocked == ((0, 1),)
    assert {target.cell[1] for target in plan.taps} <= {0, 1}
    assert all(cell[1] <= 1 for cell in plan.inferred)
    # 越界的格連 chart 都不記：四界未定時 pending() 收的就是 charted
    assert all(cell[1] <= 1 for cell in book.charted)
    assert all(cell[1] <= 1 for cell in book.pending())


def test_a_window_plan_without_a_veil_charts_and_taps_exactly_as_before():
    plain_book = ledger()
    plain = sweep.plan_window(plain_book, (0.0, 0.0), region=REGION, holes=(), bands=())

    veiled_book = ledger()
    veiled = sweep.plan_window(
        veiled_book, (0.0, 0.0), region=REGION, holes=(), bands=(), veil=None
    )

    assert veiled == plain
    assert veiled_book.charted == plain_book.charted


def test_an_unseen_border_is_explored_before_any_cell_bookkeeping():
    book = ledger(west=0, north=0, south=2)

    assert sweep.plan_pan(book, (0.0, 0.0), "east", region=REGION) == ("east", "east")


def test_the_pan_planner_flips_the_row_band_when_the_heading_is_exhausted():
    book = ledger(west=0, east=5, north=0, south=4)
    for row in range(5):
        book.record((5, row), sweep.EMPTY)

    assert sweep.plan_pan(book, (0.0, 0.0), "east", region=REGION) == ("south", "west")


def test_the_pan_planner_stops_when_nothing_is_left_beyond_the_window():
    book = ledger(west=0, east=3, north=0, south=2)
    for col in range(4):
        for row in range(3):
            book.record((col, row), sweep.EMPTY)

    assert sweep.plan_pan(book, (0.0, 0.0), "east", region=REGION) == (None, "east")


def _three_sided_board() -> sweep.SweepLedger:
    book = ledger(west=0, east=8, north=0)
    for row in range(3):
        for col in range(9):
            book.chart((col, row))
    return book


def test_the_last_missing_border_outranks_a_backlog_of_pending_cells():
    book = _three_sided_board()

    # 鏡位 (400,0) 的窗是 4..8 欄，西邊整片還沒裁決——照舊邏輯會先回頭往西清算
    assert sweep.plan_pan(book, (400.0, 0.0), "west", region=REGION) == ("south", "east")


def test_a_pinned_missing_border_hands_the_pan_plan_back_to_the_pending_cells():
    book = _three_sided_board()

    assert sweep.plan_pan(
        book, (400.0, 0.0), "west", region=REGION, pinned={"south"}
    ) == ("west", "west")
    assert "south" not in book.boundary


def _blank() -> np.ndarray:
    return np.zeros((1080, 2340, 3), np.uint8)


def _filled(point: sweep.Point, colour=(200, 120, 40), size: int = 90) -> np.ndarray:
    frame = _blank()
    x, y = int(point[0]), int(point[1])
    half = size // 2
    frame[y - half : y + half, x - half : x + half] = colour
    return frame


def test_a_card_on_the_after_frame_settles_the_verdict_before_anything_else():
    outcome = sweep.classify_tap(
        _blank(), _blank(), (800.0, 500.0), card=lambda frame: True, displace=NO_SHIFT
    )

    assert outcome.verdict == sweep.TAP_CARD


def _recentring(target: sweep.Point) -> sweep.Point:
    return (sweep.SCREEN_CENTRE[0] - target[0], sweep.SCREEN_CENTRE[1] - target[1])


def test_a_displacement_that_recentres_the_tapped_cell_with_selection_ui_is_an_ally():
    target = (400.0, 300.0)
    moved = _recentring(target)

    outcome = sweep.classify_tap(
        _blank(),
        _blank(),
        target,
        card=lambda frame: False,
        displace=lambda before, after: moved,
        selected=lambda frame: True,
    )

    assert outcome.verdict == sweep.TAP_SHIFTED


def test_selection_ui_settles_the_ally_verdict_even_when_nothing_seems_to_have_moved():
    outcome = sweep.classify_tap(
        _blank(),
        _blank(),
        (940.0, 530.0),
        card=lambda frame: False,
        displace=NO_SHIFT,
        selected=lambda frame: True,
    )

    assert outcome.verdict == sweep.TAP_SHIFTED


def test_a_recentring_displacement_without_selection_ui_is_not_sentenced_as_ally():
    target = (400.0, 300.0)

    outcome = sweep.classify_tap(
        _blank(),
        _blank(),
        target,
        card=lambda frame: False,
        displace=lambda before, after: _recentring(target),
        selected=lambda frame: False,
    )

    assert outcome.verdict == sweep.TAP_SHIFTED_UNSURE


def test_a_half_cell_displacement_is_no_feedback_not_a_recentring():
    outcome = sweep.classify_tap(
        _blank(),
        _blank(),
        (400.0, 300.0),
        card=lambda frame: False,
        displace=lambda before, after: (107.0, -8.0),
        selected=lambda frame: False,
    )

    assert outcome.verdict == sweep.TAP_NONE


def test_the_first_empty_tap_learns_the_marker_signature_and_later_taps_reuse_it():
    target = (800.0, 500.0)
    before, after = _blank(), _filled(target)

    first = sweep.classify_tap(before, after, target, displace=NO_SHIFT)

    assert first.verdict == sweep.TAP_EMPTY
    assert first.learned is not None

    moved = (1000.0, 500.0)
    second = sweep.classify_tap(
        after, _filled(moved), moved, signature=first.learned, displace=NO_SHIFT
    )

    assert second.verdict == sweep.TAP_EMPTY


def test_a_fill_that_did_not_land_on_the_tapped_cell_is_not_an_empty_verdict():
    target = (800.0, 500.0)
    signature = sweep.classify_tap(_blank(), _filled(target), target, displace=NO_SHIFT).learned

    outcome = sweep.classify_tap(
        _blank(), _filled((1400.0, 500.0)), target, signature=signature, displace=NO_SHIFT
    )

    assert outcome.verdict == sweep.TAP_NONE


def test_a_tap_that_changed_nothing_is_no_feedback_not_an_empty_cell():
    outcome = sweep.classify_tap(_blank(), _blank(), (800.0, 500.0), displace=NO_SHIFT)

    assert outcome.verdict == sweep.TAP_NONE


def test_the_grid_phase_of_a_frame_measures_how_far_the_camera_slipped():
    drift = sweep.aim_drift((35.0, 0.0), GRID, offset=(-500.0, -300.0))

    assert drift == (35.0, 0.0)
    assert not sweep.aimed(drift, GRID)


def test_a_phase_that_matches_the_camera_leaves_the_aim_untouched():
    drift = sweep.aim_drift((0.0, 0.0), GRID, offset=(-500.0, -300.0))

    assert drift == (0.0, 0.0)
    assert sweep.aimed(drift, GRID)


def test_the_measured_pitch_is_the_period_both_sides_of_the_aim_gate_use():
    grid = WorldGrid(phase=(0.0, 0.0), col_pitch=87.0, row_pitch=87.0)
    measured = (84.0, 84.0)
    offset = (-2000.0, -1200.0)
    phase = (2000.0 % measured[0], 1200.0 % measured[1])

    drift = sweep.aim_drift(phase, grid, offset, measured)

    assert drift == (0.0, 0.0)
    assert sweep.aimed(drift, grid, pitch=measured)

    modelled = sweep.aim_drift(phase, grid, offset)

    assert modelled == (-18.0, 42.0)
    assert not sweep.aimed(modelled, grid)


def test_the_aim_slack_scales_with_the_pitch_it_was_given():
    grid = WorldGrid(phase=(0.0, 0.0), col_pitch=87.0, row_pitch=87.0)

    assert sweep.aimed((20.0, 0.0), grid)
    assert not sweep.aimed((20.0, 0.0), grid, pitch=(60.0, 60.0))


def test_the_recentred_camera_is_reconstructed_from_the_cell_that_was_tapped():
    offset = sweep.recentre_offset(GRID, (7, 4), centre=(1000.0, 500.0))

    assert offset == (-250.0, -50.0)


def test_both_landmarks_lock_the_camera_and_beat_the_recentre_candidate():
    offset, source = sweep.reanchor(
        GRID,
        landmarks={"west": 0.0, "north": 0.0},
        borders={"west": 100.0, "north": 50.0},
        candidate=(999.0, 999.0),
    )

    assert (offset, source) == ((-100.0, -50.0), sweep.SOURCE_EDGE)


def test_one_landmark_axis_is_completed_by_the_candidate():
    offset, source = sweep.reanchor(
        GRID,
        landmarks={"west": 0.0},
        borders={"west": 100.0},
        candidate=(999.0, 7.0),
    )

    assert (offset, source) == ((-100.0, 7.0), sweep.SOURCE_MIXED)


def test_two_landmarks_on_one_axis_that_disagree_are_both_refused():
    axes = sweep.border_offsets(
        GRID, {"west": 0.0, "east": 1000.0}, {"west": 100.0, "east": 900.0}
    )

    assert axes == {}


def test_with_no_evidence_at_all_the_camera_is_lost_and_says_so():
    assert sweep.reanchor(GRID, landmarks={}, borders={}, candidate=None) == (
        None,
        sweep.SOURCE_LOST,
    )


def test_the_northwest_corner_defines_the_world_origin():
    lattice = board.Lattice(tuple(range(100, 601, 100)), tuple(range(50, 551, 100)))

    anchored = sweep.anchor_northwest(lattice, board.GRID_REGION, {"west": 100.0, "north": 50.0})

    assert anchored is not None
    grid, offset = anchored
    assert offset == (-100.0, -50.0)
    assert grid.phase == pytest.approx((0.0, 0.0), abs=1e-9)
    assert sweep.border_cell(grid, "west", 0.0) == 0
    assert sweep.border_cell(grid, "east", 1000.0) == 9


def test_the_corner_needs_both_sides_in_the_same_frame():
    lattice = board.Lattice(tuple(range(100, 601, 100)), tuple(range(50, 551, 100)))

    assert sweep.anchor_northwest(lattice, board.GRID_REGION, {"west": 100.0}) is None


def test_the_summary_lists_every_sentenced_cell_by_kind():
    book = ledger(west=0, east=1, north=0, south=0)
    book.record((0, 0), sweep.ENEMY, name="sig-a")
    book.record((1, 0), sweep.ALLY)
    book.taps = 12

    summary = book.summary()

    assert summary["complete"]
    assert summary["counts"][sweep.ENEMY] == 1
    assert summary["enemies"] == [{"cell": [0, 0], "name": "sig-a"}]
    assert summary["allies"] == [[1, 0]]
    assert summary["taps"] == 12


def test_the_stride_is_capped_by_the_marker_staying_inside_the_next_window():
    # 窗 (0,0,400,300)，標記在 x=300：往東推的內容往西走，標記走到窗左緣就是上限。
    cap = sweep.stride_cap((300.0, 150.0), "east", region=REGION, gain=1.0)

    assert cap == 300.0
    assert sweep.stride_cap((300.0, 150.0), "west", region=REGION, gain=1.0) == 100.0
    assert sweep.stride_cap((300.0, 150.0), "north", region=REGION, gain=1.0) == 150.0
    assert sweep.stride_cap((300.0, 150.0), "south", region=REGION, gain=1.0) == 150.0


def test_the_stride_cap_shrinks_by_the_gain_and_the_keep_margin():
    cap = sweep.stride_cap((300.0, 150.0), "east", region=REGION, gain=0.5, margin=50.0)

    assert cap == 500.0
    assert sweep.stride_cap((0.0, 150.0), "east", region=REGION, gain=1.0) == 0.0


def test_a_marker_already_on_the_leading_edge_is_not_carried_again():
    book = ledger()
    for col in range(4):
        book.record((col, 0), sweep.EMPTY)

    assert sweep.frontier_tap(book, (0.0, 0.0), (3, 0), "east", region=REGION,
                              holes=(), bands=()) is None


def test_a_marker_behind_the_leading_edge_is_carried_to_the_furthest_empty_cell():
    book = ledger()
    for col in range(4):
        book.record((col, 0), sweep.EMPTY)
    book.record((3, 0), sweep.ENEMY)

    target = sweep.frontier_tap(book, (0.0, 0.0), (0, 0), "east", region=REGION,
                                holes=(), bands=())

    # (3,0) 是敵方格不能拿來搬標記，前緣退到 (2,0)
    assert target is not None
    assert target.cell == (2, 0)


def test_a_marker_left_outside_the_window_is_replanted_instead_of_trusted():
    # 返航實況：回角落歸零後標記還在遠方舊鋒面（20,0），本窗看不見它。
    book = ledger()
    for col in range(4):
        book.record((col, 0), sweep.EMPTY)

    target = sweep.frontier_tap(book, (0.0, 0.0), (20, 0), "east", region=REGION,
                                holes=(), bands=())

    assert target is not None
    assert target.cell == (3, 0)


def test_the_window_membership_test_follows_the_camera():
    assert sweep.in_window(GRID, (0.0, 0.0), (3, 0), REGION)
    assert not sweep.in_window(GRID, (0.0, 0.0), (20, 0), REGION)
    assert sweep.in_window(GRID, (1700.0, 0.0), (20, 0), REGION)
    assert not sweep.in_window(GRID, (0.0, 0.0), None, REGION)


def test_carrying_the_marker_never_spends_an_undecided_cell():
    book = ledger()
    book.record((0, 0), sweep.EMPTY)

    assert sweep.frontier_tap(book, (0.0, 0.0), (0, 0), "east", region=REGION,
                              holes=(), bands=()) is None


def test_a_border_that_does_not_match_the_ledger_refuses_the_anchor():
    book = ledger()
    landmarks = {"north": 0.0}

    assert sweep.contradicts(book, landmarks, {"north": 40.0}, (0.0, -40.0)) is None
    assert sweep.contradicts(book, landmarks, {"north": 40.0}, (0.0, 200.0)) == "north"
    # 帳本沒記過的那一側說不了話
    assert sweep.contradicts(book, landmarks, {"east": 900.0}, (0.0, -40.0)) is None


def test_the_node_chain_grows_on_every_successful_expansion():
    walk = sweep.NodeWalk(full_reach=200.0)

    walk.expanded(sweep.TrustNode(cell=(1, 0), offset=(0.0, 0.0)))
    walk.expanded(sweep.TrustNode(cell=(5, 0), offset=(400.0, 0.0)))

    assert [node.cell for node in walk.nodes] == [(1, 0), (5, 0)]
    assert walk.reach == 200.0
    assert walk.failures == 0


def test_a_lost_marker_retreats_the_same_amount_and_then_halves_the_stride():
    walk = sweep.NodeWalk(full_reach=200.0)
    walk.expanded(sweep.TrustNode(cell=(1, 0), offset=(0.0, 0.0)))

    assert walk.lost() == sweep.STEP_RETREAT
    assert walk.recovered() == sweep.STEP_EXPAND
    assert walk.reach == 100.0
    assert walk.failures == 1
    assert len(walk.nodes) == 1


def test_two_failures_on_the_same_node_escalate_to_the_corner():
    walk = sweep.NodeWalk(full_reach=200.0)
    walk.expanded(sweep.TrustNode(cell=(1, 0), offset=(0.0, 0.0)))

    walk.lost()
    walk.recovered()
    walk.lost()

    assert walk.recovered() == sweep.STEP_ROOT


def test_losing_the_marker_on_the_way_back_walks_the_chain_down_to_the_corner():
    walk = sweep.NodeWalk(full_reach=200.0)
    walk.expanded(sweep.TrustNode(cell=(1, 0), offset=(0.0, 0.0)))
    walk.expanded(sweep.TrustNode(cell=(5, 0), offset=(400.0, 0.0)))

    assert walk.lost() == sweep.STEP_RETREAT
    assert walk.lost() == sweep.STEP_RETREAT
    assert len(walk.nodes) == 1
    assert walk.lost() == sweep.STEP_RETREAT
    assert walk.nodes == []
    assert walk.lost() == sweep.STEP_ROOT


def test_the_corner_reset_throws_the_whole_chain_away():
    walk = sweep.NodeWalk(full_reach=200.0)
    walk.expanded(sweep.TrustNode(cell=(1, 0), offset=(0.0, 0.0)))
    walk.lost()
    walk.recovered()

    walk.rooted()

    assert walk.nodes == []
    assert walk.reach == 200.0
    assert walk.failures == 0
    assert walk.lost() == sweep.STEP_RETREAT


def test_a_tap_request_while_lost_is_refused_outright():
    fix = sweep.Fix()

    fix.allow_tap()
    fix.lose()

    assert not fix.anchored
    with pytest.raises(sweep.Adrift):
        fix.allow_tap()

    fix.regain()
    fix.allow_tap()


def test_a_gesture_that_did_not_move_the_lattice_phase_counts_as_eaten():
    assert not sweep.gesture_landed((0.5, 40.0), "east")
    assert sweep.gesture_landed((40.0, 0.5), "east")
    assert not sweep.gesture_landed((40.0, 0.5), "north")
    assert sweep.gesture_landed((0.5, 40.0), "north")


def test_a_stalled_push_is_read_as_the_edge_only_when_the_border_says_so():
    ledger = sweep.SweepLedger(grid=GRID)
    assert not sweep.at_border("north", {}, ledger=ledger, offset=(0.0, 0.0))
    assert sweep.at_border("north", {"north": 120.0}, ledger=ledger, offset=(0.0, 0.0))

    ledger.boundary["north"] = 2  # 鏡位 (0,0) 的窗最北就是第 2 列
    assert sweep.at_border("north", {}, ledger=ledger, offset=(0.0, 0.0))
    assert not sweep.at_border("north", {}, ledger=ledger, offset=(0.0, 1000.0))


def test_an_unreadable_lattice_is_not_read_as_a_dead_gesture():
    assert sweep.gesture_landed(None, "east")


def test_the_phase_difference_wraps_into_half_a_pitch_each_axis():
    shift = board.phase_shift((80.0, 10.0), (10.0, 80.0), (90.0, 90.0))

    assert shift == (20.0, -20.0)


def test_the_homing_route_walks_one_leg_per_screen_back_to_the_frontier():
    grid = WorldGrid(phase=(0.0, 0.0), col_pitch=100.0, row_pitch=100.0)

    route = sweep.homing_route(grid, (0.0, 0.0), (9, 0), region=REGION, stride=200.0)

    assert route == ("east", "east", "east")


def test_a_frontier_already_in_the_window_needs_no_homing():
    grid = WorldGrid(phase=(0.0, 0.0), col_pitch=100.0, row_pitch=100.0)

    assert sweep.homing_route(grid, (0.0, 0.0), (1, 1), region=REGION, stride=200.0) == ()


def test_the_tap_window_reaches_east_of_the_map_region():
    grid = WorldGrid(phase=(0.0, 0.0), col_pitch=100.0, row_pitch=100.0)

    targets = sweep.window_targets(grid, (0.0, 0.0))

    assert sweep.TAP_REGION != board.MAP_REGION
    assert targets[(17, 4)] == (1750.0, 450.0)  # 格框 1700-1800 跨舊窗右緣 1750
    assert targets[(19, 4)] == (1950.0, 450.0)


def test_a_cell_hanging_past_the_new_tap_window_is_still_left_out():
    grid = WorldGrid(phase=(0.0, 0.0), col_pitch=100.0, row_pitch=100.0)

    targets = sweep.window_targets(grid, (0.0, 0.0))

    assert (20, 4) not in targets  # 格框 2000-2100 跨窗右緣 2050


def test_the_frontier_is_the_first_undecided_cell_in_serpentine_order():
    book = ledger(west=0, east=2, north=0, south=1)
    book.record((0, 0), sweep.EMPTY)
    book.record((1, 0), sweep.EMPTY)

    assert sweep.frontier_cell(book, "east") == (2, 0)
    assert sweep.frontier_cell(ledger(west=0, east=0, north=0, south=0)) == (0, 0)


def test_a_density_peak_spreads_over_the_cells_it_could_belong_to():
    cells = sweep.candidate_cells(GRID, (0.0, 0.0), [(150.0, 150.0)], halo=0.75)

    assert cells == frozenset({(col, row) for col in range(3) for row in range(3)})


def test_a_peak_well_inside_one_cell_only_claims_that_cell():
    cells = sweep.candidate_cells(GRID, (0.0, 0.0), [(250.0, 350.0)], halo=0.4)

    assert cells == frozenset({(2, 3)})


def test_the_candidate_filter_taps_the_candidates_and_infers_the_rest_empty():
    book = ledger()

    plan = sweep.plan_window(
        book, (0.0, 0.0), region=REGION, holes=(), bands=(), candidates={(1, 1), (9, 9)}
    )

    assert [target.cell for target in plan.taps] == [(1, 1)]
    assert (1, 1) not in plan.inferred
    assert set(plan.inferred) == {
        (col, row) for col in range(4) for row in range(3)
    } - {(1, 1)}


def test_a_blocked_cell_is_never_inferred_empty():
    band = DangerBand("test", (0, 150), (0, 150), intents=())

    plan = sweep.plan_window(
        ledger(), (0.0, 0.0), region=REGION, holes=(), bands=(band,), candidates=set()
    )

    assert (0, 0) in plan.blocked
    assert (0, 0) not in plan.inferred


def test_the_ledger_keeps_clicked_and_inferred_empties_apart():
    book = ledger(west=0, east=1, north=0, south=0)
    book.record((0, 0), sweep.EMPTY)
    book.record((1, 0), sweep.EMPTY_INFERRED, reason="candidate_filter")

    counts = book.summary()["counts"]

    assert counts[sweep.EMPTY] == 1
    assert counts[sweep.EMPTY_INFERRED] == 1
    assert book.complete


def test_the_marker_can_be_carried_onto_an_inferred_empty_when_asked():
    book = ledger()
    book.record((1, 0), sweep.EMPTY_INFERRED)

    plain = sweep.frontier_tap(book, (0.0, 0.0), (0, 0), "east", region=REGION, holes=(),
                               bands=())
    widened = sweep.frontier_tap(
        book, (0.0, 0.0), (0, 0), "east", region=REGION, holes=(), bands=(),
        accept=(sweep.EMPTY, sweep.EMPTY_INFERRED),
    )

    assert plain is None
    assert widened is not None and widened.cell == (1, 0)


def test_the_marker_displacement_outranks_the_wrapped_lattice_phase():
    # 0805 死因：整把 ~250px 的南推被 mod 格距的相位讀成 9.5px＝沒動。
    assert (
        sweep.gesture_verdict((0.0, 9.5), "south", travel=247.0, moved=(-6.0, 250.0))
        == sweep.PAN_LANDED
    )
    assert (
        sweep.gesture_verdict((0.0, 40.0), "south", travel=247.0, moved=(1.0, 12.0))
        == sweep.PAN_PINNED
    )


def test_without_a_marker_the_phase_alone_still_calls_a_gesture_eaten():
    assert sweep.gesture_verdict((0.0, 1.0), "south", travel=247.0) == sweep.PAN_EATEN
    assert sweep.gesture_verdict((0.0, 40.0), "south", travel=247.0) == sweep.PAN_LANDED


def test_a_pinned_direction_is_skipped_by_the_pan_plan_without_becoming_a_border():
    ledger = sweep.SweepLedger(grid=GRID)
    ledger.boundary.update(west=0, east=1, north=0)
    ledger.chart((0, 9))

    assert sweep.plan_pan(ledger, (0.0, 0.0), "east")[0] == "south"
    assert sweep.plan_pan(ledger, (0.0, 0.0), "east", pinned={"south"})[0] is None
    assert "south" not in ledger.boundary


def stars(cells, offset, jitter=()):
    """帳本單位格 → 該鏡位下的螢幕峰點（可逐點加抖動）。"""
    points = []
    for index, cell in enumerate(cells):
        centre = GRID.centre_of(cell)
        dx, dy = jitter[index] if index < len(jitter) else (0.0, 0.0)
        points.append((centre[0] - offset[0] + dx, centre[1] - offset[1] + dy))
    return tuple(points)


REGION_STARS = (0, 0, 2000, 1000)


def constellation(references, peaks, stars_needed=3):
    """圖形規則的測試用三顆門檻；正式門檻另有一支測試鎖住。"""
    return sweep.constellation_offset(
        references, peaks, GRID, region=REGION_STARS,
        min_peaks=stars_needed, min_match=stars_needed,
    )


def test_the_shipped_threshold_refuses_a_four_star_figure():
    refs = ((2, 1), (5, 3), (7, 2), (3, 6))
    fix = sweep.constellation_offset(refs, stars(refs, (250.0, 120.0)), GRID, region=REGION_STARS)

    assert fix.offset is None
    assert fix.reason == sweep.CONSTELLATION_FEW_PEAKS

    wide = refs + ((9, 5),)
    lit = sweep.constellation_offset(
        wide, stars(wide, (250.0, 120.0)), GRID, region=REGION_STARS
    )

    assert lit.reason == sweep.CONSTELLATION_OK
    assert lit.offset == pytest.approx((250.0, 120.0))


def test_a_unique_constellation_alignment_rebuilds_the_camera_offset():
    refs = ((2, 1), (5, 3), (7, 2), (3, 6))
    fix = constellation(refs, stars(refs, (250.0, 120.0)))

    assert fix.reason == sweep.CONSTELLATION_OK
    assert fix.matched == 4
    assert fix.offset == pytest.approx((250.0, 120.0))


def test_a_constellation_alignment_tolerates_half_a_cell_of_peak_wobble():
    refs = ((2, 1), (5, 3), (7, 2), (3, 6))
    jitter = ((40.0, -30.0), (-45.0, 20.0), (10.0, 44.0), (0.0, 0.0))
    fix = constellation(refs, stars(refs, (250.0, 120.0), jitter))

    assert fix.reason == sweep.CONSTELLATION_OK
    assert fix.matched == 4
    # 精修取殘差平均：抖動互相抵銷後仍落在真值半格內。
    assert fix.offset == pytest.approx((250.0 - 1.25, 120.0 - 8.5))


def test_a_repeating_row_of_references_aligns_two_ways_and_is_refused():
    refs = ((0, 0), (1, 0), (2, 0))
    peaks = stars(((0, 0), (1, 0), (2, 0), (3, 0), (4, 0)), (0.0, 0.0))
    fix = constellation(refs, peaks)

    assert fix.offset is None
    assert fix.reason == sweep.CONSTELLATION_AMBIGUOUS


def test_too_few_peaks_never_form_a_recognisable_figure():
    refs = ((2, 1), (5, 3), (7, 2), (3, 6))
    fix = constellation(refs, stars(((2, 1), (5, 3)), (0.0, 0.0)))

    assert fix.offset is None
    assert fix.reason == sweep.CONSTELLATION_FEW_PEAKS


def test_a_ledger_with_too_few_confirmed_units_has_no_star_chart():
    fix = constellation(((2, 1), (5, 3)), stars(((2, 1), (5, 3), (7, 2)), (0.0, 0.0)))

    assert fix.offset is None
    assert fix.reason == sweep.CONSTELLATION_FEW_UNITS


def test_a_reference_cell_without_a_peak_sinks_the_hypothesis():
    # 帳→幀全覆蓋：參考格投影進偵測區卻沒有精靈＝這個鏡位假說是錯的。
    refs = ((2, 1), (5, 3), (7, 2), (3, 6))
    peaks = stars(((2, 1), (5, 3), (7, 2)), (250.0, 120.0)) + ((900.0, 700.0),)
    fix = constellation(refs, peaks)

    assert fix.offset is None
    assert fix.reason == sweep.CONSTELLATION_NO_MATCH


def test_extra_undecided_peaks_do_not_score_and_do_not_block_the_alignment():
    refs = ((2, 1), (5, 3), (7, 2), (3, 6))
    peaks = stars(refs, (250.0, 120.0)) + ((900.0, 700.0), (1500.0, 40.0))
    fix = constellation(refs, peaks)

    assert fix.reason == sweep.CONSTELLATION_OK
    assert fix.matched == 4
    assert fix.offset == pytest.approx((250.0, 120.0))


def test_reference_cells_projected_off_frame_are_excused_from_coverage():
    refs = ((2, 1), (5, 3), (7, 2), (3, 6), (60, 40))
    fix = constellation(refs, stars(refs[:4], (250.0, 120.0)))

    assert fix.reason == sweep.CONSTELLATION_OK
    assert fix.matched == 4


def test_the_star_chart_only_trusts_enemies_whose_name_was_read():
    book = ledger()
    book.record((1, 1), sweep.ENEMY, name="sig-a")
    book.record((4, 2), sweep.ENEMY, name="sig-b")
    book.record((6, 5), sweep.ENEMY, reason="card_without_dock")
    book.record((2, 3), sweep.ALLY, reason="recentred")
    book.record((3, 3), sweep.EMPTY)

    assert sweep.identified_units(book) == ((1, 1), (4, 2))


def test_the_census_closes_only_when_all_three_sides_and_all_four_borders_are_in():
    book = ledger(west=0, east=2, north=0, south=0)
    book.record((0, 0), sweep.ENEMY, name="a")
    book.record((1, 0), sweep.ALLY)
    book.record((2, 0), sweep.NPC, name="c")

    assert sweep.census(book) == sweep.Census(1, 1, 1)
    assert sweep.census_closed(book, sweep.Census(1, 1, 1))
    assert not sweep.census_closed(book, sweep.Census(2, 1, 1))
    assert not sweep.census_closed(book, sweep.Census(1, 2, 1))
    assert not sweep.census_closed(book, sweep.Census(1, 1, 0))


def test_a_stage_with_no_truth_file_never_closes_the_census():
    book = ledger(west=0, east=0, north=0, south=0)
    book.record((0, 0), sweep.ENEMY, name="a")

    assert not sweep.census_closed(book, None)


def test_an_over_counted_ledger_never_closes_the_census():
    book = ledger(west=0, east=2, north=0, south=0)
    book.record((0, 0), sweep.ENEMY)
    book.record((1, 0), sweep.ENEMY)

    assert not sweep.census_closed(book, sweep.Census(1, 0, 0))


def test_the_census_stays_open_while_a_border_is_still_missing():
    book = ledger(west=0, east=2, north=0)
    book.record((0, 0), sweep.ENEMY)

    assert not sweep.census_closed(book, sweep.Census(1, 0, 0))


def test_a_third_party_unit_is_asked_for_a_peak_like_any_other():
    book = ledger(west=0, east=2, north=0, south=0)
    book.record((0, 0), sweep.NPC, name="c")

    assert sweep.roster_missing(book, (), (-150.0, -150.0)) == ((0, 0),)


def test_the_strongest_peak_is_tapped_first_no_matter_where_the_serpentine_put_it():
    book = ledger(west=0, east=3, north=0, south=0)
    peaks = ((250.0, 50.0), (50.0, 50.0))
    order = sweep.candidate_ranking(GRID, (0.0, 0.0), peaks, halo=0.0)

    assert order[(2, 0)] < order[(0, 0)]

    plan = sweep.plan_window(
        book, (0.0, 0.0), region=REGION, holes=(), bands=(),
        candidates=set(order), order=order,
    )

    assert [target.cell for target in plan.taps] == [(2, 0), (0, 0)]


def test_a_cell_covered_by_two_peaks_ranks_by_the_stronger_one():
    order = sweep.candidate_ranking(GRID, (0.0, 0.0), ((250.0, 50.0), (60.0, 50.0)), halo=0.5)

    assert order[(0, 0)] == 1
    assert order[(2, 0)] == 0


def test_the_roster_check_passes_when_every_booked_unit_has_a_peak_under_it():
    book = ledger(west=0, east=2, north=0, south=0)
    book.record((0, 0), sweep.ENEMY, name="a")
    book.record((1, 0), sweep.ALLY)

    peaks = ((200.0, 200.0), (300.0, 200.0), (900.0, 900.0))

    assert sweep.roster_missing(book, peaks, (-150.0, -150.0)) == ()


def test_a_booked_unit_with_no_sprite_under_it_fails_the_roster_check():
    book = ledger(west=0, east=2, north=0, south=0)
    book.record((0, 0), sweep.ENEMY, name="a")
    book.record((1, 0), sweep.ENEMY, name="b")

    assert sweep.roster_missing(book, ((200.0, 200.0),), (-150.0, -150.0)) == ((1, 0),)


def test_a_unit_projected_outside_the_detection_region_is_not_asked_for_a_peak():
    book = ledger(west=0, east=2, north=0, south=0)
    book.record((0, 0), sweep.ENEMY, name="a")

    assert sweep.roster_missing(book, (), (5000.0, 5000.0)) == ()


def test_two_booked_units_may_not_share_one_peak():
    book = ledger(west=0, east=2, north=0, south=0)
    book.record((0, 0), sweep.ENEMY, name="a")
    book.record((1, 0), sweep.ENEMY, name="b")

    missing = sweep.roster_missing(book, ((250.0, 200.0),), (-150.0, -150.0))

    assert len(missing) == 1


def _blank_frame() -> np.ndarray:
    return np.zeros((1080, 2340, 3), np.uint8)


def _stirred(pixels: int) -> np.ndarray:
    """在全黑幀上點亮一片：與全黑幀相比就有 `pixels` 個「明顯變了」的像素。"""
    frame = _blank_frame()
    frame.reshape(-1, 3)[:pixels] = 255
    return frame


def waiting(frames: list[np.ndarray]):
    """假時鐘＋假幀序列：幀序列排好，最後一張耗盡就一直回它。"""
    served = iter(frames)
    naps: list[float] = []
    now = [0.0]

    def sleep(seconds: float) -> None:
        naps.append(seconds)
        now[0] += seconds

    return (lambda: next(served, frames[-1]), sleep, (lambda: now[0]), naps, now)


def test_the_wait_holds_until_the_glide_stops_before_it_hands_back_a_frame():
    landed = _stirred(200_003)  # 與前一幀只差 3 px：待機動畫等級的殘動
    grab, sleep, clock, naps, now = waiting(
        [_blank_frame(), _stirred(100_000), _stirred(200_000), landed]
    )

    frame = settle.await_still(
        grab, clock=clock, sleep=sleep, deadline=settle.SETTLE_WAIT_S, poll=settle.SETTLE_POLL_S
    )

    assert frame is landed
    assert naps == [settle.SETTLE_POLL_S] * 3
    assert now[0] < settle.SETTLE_WAIT_S


def test_a_frame_that_never_goes_quiet_is_handed_back_at_the_deadline():
    grab, sleep, clock, naps, now = waiting([_blank_frame(), _stirred(100_000)] * 20)

    frame = settle.await_still(
        grab, clock=clock, sleep=sleep, deadline=settle.SETTLE_WAIT_S, poll=settle.SETTLE_POLL_S
    )

    assert frame.shape == _blank_frame().shape
    assert now[0] >= settle.SETTLE_WAIT_S
    assert naps == [settle.SETTLE_POLL_S] * math.ceil(settle.SETTLE_WAIT_S / settle.SETTLE_POLL_S)


def test_a_screen_that_is_already_still_costs_one_poll():
    grab, sleep, clock, naps, now = waiting([_blank_frame(), _blank_frame()])

    settle.await_still(
        grab, clock=clock, sleep=sleep, deadline=settle.SETTLE_WAIT_S, poll=settle.SETTLE_POLL_S
    )

    assert naps == [settle.SETTLE_POLL_S]
    assert now[0] == settle.SETTLE_POLL_S


def test_a_second_confirmation_pair_is_demanded_before_the_wait_lets_go():
    landed = _blank_frame()
    grab, sleep, clock, naps, _ = waiting([_blank_frame(), _blank_frame(), landed])

    frame = settle.await_still(
        grab,
        clock=clock,
        sleep=sleep,
        deadline=settle.SETTLE_WAIT_S,
        poll=settle.SETTLE_POLL_S,
        confirm=2,
    )

    assert frame is landed
    assert naps == [settle.SETTLE_POLL_S] * 2


def test_motion_between_the_pairs_restarts_the_confirmation_count():
    landed = _blank_frame()
    grab, sleep, clock, naps, _ = waiting(
        [
            _blank_frame(),
            _stirred(200_000),
            _stirred(200_003),  # 第一對靜止：緩動尾巴的瞬間低谷
            _stirred(100_000),  # 鏡頭其實還在滑
            _blank_frame(),
            _blank_frame(),
            landed,
        ]
    )

    frame = settle.await_still(
        grab,
        clock=clock,
        sleep=sleep,
        deadline=settle.SETTLE_WAIT_S,
        poll=settle.SETTLE_POLL_S,
        confirm=2,
    )

    assert frame is landed
    assert naps == [settle.SETTLE_POLL_S] * 6


def test_the_deadline_release_is_booked_as_unconverged():
    grab, sleep, clock, _, now = waiting([_blank_frame(), _stirred(100_000)] * 20)
    seen: list[settle.SettleReport] = []

    settle.await_still(
        grab,
        clock=clock,
        sleep=sleep,
        deadline=settle.SETTLE_WAIT_S,
        poll=settle.SETTLE_POLL_S,
        confirm=2,
        observe=seen.append,
    )

    assert now[0] >= settle.SETTLE_WAIT_S
    assert [report.converged for report in seen] == [False]


def test_a_camera_sliding_moves_far_more_pixels_than_the_stable_threshold():
    rng = np.random.default_rng(0)
    still = _blank_frame()
    still[300:800, 400:1400] = rng.integers(0, 256, (500, 1000, 3), dtype=np.uint8)
    idle = still.copy()
    idle[500:520, 600:620] = 255  # 一隻精靈的待機動畫
    slid = np.roll(still, 60, axis=1)  # 鏡頭滑一段

    assert settle.frame_motion(still, idle) < settle.SETTLE_STABLE_DIFF
    assert settle.frame_motion(still, slid) > settle.SETTLE_STABLE_DIFF * 10


def test_a_frame_of_another_shape_counts_as_all_motion():
    assert settle.frame_motion(_blank_frame(), np.zeros((540, 1170, 3), np.uint8)) == 1.0


def test_the_judgement_only_ever_sees_frames_that_have_settled():
    grab, sleep, clock, _, _ = waiting(
        [_blank_frame(), _stirred(100_000), _stirred(200_000), _stirred(200_003)]
    )
    seen: list[np.ndarray] = []

    def judge(after: np.ndarray) -> sweep.TapOutcome:
        seen.append(after)
        return sweep.TapOutcome(sweep.TAP_EMPTY)

    outcome = sweep.judge_tap(
        grab,
        judge,
        clock=clock,
        sleep=sleep,
        deadline=sweep.FEEDBACK_WAIT_S,
        poll=sweep.FEEDBACK_POLL_S,
    )

    assert outcome.verdict == sweep.TAP_EMPTY
    assert len(seen) == 1  # 中間三張動畫幀一次都沒問


def test_a_silent_tap_is_polled_again_until_the_budget_runs_out():
    grab, sleep, clock, _, now = waiting([_blank_frame()])
    asked: list[float] = []

    def judge(after: np.ndarray) -> sweep.TapOutcome:
        asked.append(now[0])
        return sweep.TapOutcome(sweep.TAP_NONE)

    outcome = sweep.judge_tap(
        grab,
        judge,
        clock=clock,
        sleep=sleep,
        deadline=sweep.FEEDBACK_WAIT_S,
        poll=sweep.FEEDBACK_POLL_S,
    )

    assert outcome.verdict == sweep.TAP_NONE
    assert len(asked) > 1
    assert now[0] >= sweep.FEEDBACK_WAIT_S


def test_a_settled_wait_reports_what_it_cost():
    grab, sleep, clock, _, _ = waiting(
        [_blank_frame(), _stirred(100_000), _stirred(200_000), _stirred(200_003)]
    )
    seen: list[settle.SettleReport] = []

    settle.await_still(
        grab,
        clock=clock,
        sleep=sleep,
        deadline=settle.SETTLE_WAIT_S,
        poll=settle.SETTLE_POLL_S,
        observe=seen.append,
    )

    assert len(seen) == 1
    assert seen[0].converged
    assert seen[0].polls == 3
    assert seen[0].waited_s == pytest.approx(settle.SETTLE_POLL_S * 3)
    assert seen[0].motion < settle.SETTLE_STABLE_DIFF


def test_a_wait_that_ran_out_of_budget_reports_that_it_never_converged():
    grab, sleep, clock, _, _ = waiting([_blank_frame(), _stirred(100_000)] * 20)
    seen: list[settle.SettleReport] = []

    settle.await_still(
        grab,
        clock=clock,
        sleep=sleep,
        deadline=settle.SETTLE_WAIT_S,
        poll=settle.SETTLE_POLL_S,
        observe=seen.append,
    )

    assert len(seen) == 1
    assert not seen[0].converged
    assert seen[0].waited_s >= settle.SETTLE_WAIT_S
    assert seen[0].motion > settle.SETTLE_STABLE_DIFF


def test_the_tap_judgement_hands_every_wait_it_made_to_the_observer():
    grab, sleep, clock, _, _ = waiting([_blank_frame()])
    seen: list[settle.SettleReport] = []
    answers = iter([sweep.TAP_NONE, sweep.TAP_NONE, sweep.TAP_EMPTY])

    def judge(after: np.ndarray) -> sweep.TapOutcome:
        return sweep.TapOutcome(next(answers))

    outcome = sweep.judge_tap(
        grab,
        judge,
        clock=clock,
        sleep=sleep,
        deadline=sweep.FEEDBACK_WAIT_S,
        poll=sweep.FEEDBACK_POLL_S,
        observe=seen.append,
    )

    assert outcome.verdict == sweep.TAP_EMPTY
    assert len(seen) == 3
    assert all(report.converged for report in seen)
