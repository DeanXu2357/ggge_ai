"""每格點擊清算掃描的離線測試：帳本、規劃器、三分類器與重錨算術。"""

from __future__ import annotations

import numpy as np

from ggge_ai.runtime import board, sweep
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
    band = DangerBand("test", (0, 150), (0, 150), intent="")

    plan = sweep.plan_window(book, (0.0, 0.0), region=REGION, holes=((200, 0, 100, 100),),
                             bands=(band,))

    assert (0, 0) in plan.blocked
    assert (2, 0) in plan.blocked
    assert (0, 0) not in [target.cell for target in plan.taps]

    book.defer((0, 0))
    assert book.blocked[(0, 0)] == 1
    assert book.summary()["deferred"] == [[0, 0]]


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


def test_a_large_content_displacement_reads_as_the_camera_recentring():
    outcome = sweep.classify_tap(
        _blank(),
        _blank(),
        (800.0, 500.0),
        card=lambda frame: False,
        displace=lambda before, after: (-240.0, 30.0),
    )

    assert outcome.verdict == sweep.TAP_SHIFTED
    assert outcome.delta == (-240.0, 30.0)


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

    anchored = sweep.anchor_northwest(lattice, {"west": 100.0, "north": 50.0})

    assert anchored is not None
    grid, offset = anchored
    assert offset == (-100.0, -50.0)
    assert grid.phase == (0.0, 0.0)
    assert sweep.border_cell(grid, "west", 0.0) == 0
    assert sweep.border_cell(grid, "east", 1000.0) == 9


def test_the_corner_needs_both_sides_in_the_same_frame():
    lattice = board.Lattice(tuple(range(100, 601, 100)), tuple(range(50, 551, 100)))

    assert sweep.anchor_northwest(lattice, {"west": 100.0}) is None


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
