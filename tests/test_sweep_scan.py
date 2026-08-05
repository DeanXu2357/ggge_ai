"""點擊清算掃描主迴圈的組裝：本窗點完 → 沒得推就停 → 帳本收斂。

裝置整支換成假件（幀是全黑合成圖），完全不碰 adb。
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from ggge_ai.runtime import board, sweep
from ggge_ai.runtime.coverage import WorldGrid
from ggge_ai.runtime.journal import Journal
from scripts.sweep_scan import STRANDINGS_LIMIT, Halt, SweepRun

GRID = WorldGrid(phase=(0.0, 0.0), col_pitch=100.0, row_pitch=100.0)


def _blank() -> np.ndarray:
    return np.zeros((1080, 2340, 3), np.uint8)


def build_run(tmp_path, outcomes: dict) -> SweepRun:
    journal = Journal(tmp_path / "sweep.jsonl")
    camera = SimpleNamespace(grab=_blank, keep=lambda label: None, shots=0)
    run = SweepRun(
        device=SimpleNamespace(tap=lambda x, y: None),
        camera=camera,
        journal=journal,
        executor=None,
        driver=None,
        perceiver=None,
        gate=None,
        identifier=None,
        sleep=lambda seconds: None,
    )
    run.ledger = sweep.SweepLedger(grid=GRID)
    run.ledger.boundary.update(west=2, east=4, north=4, south=5)
    run.settled = _blank
    run.witness = lambda frame: None
    run.pan = lambda direction, frame, reach=None: (reach or 0.0, _blank())
    run.relocate = lambda candidate=None: None
    run.escape = lambda: None
    run.on_hub = lambda frame=None: True
    run.neutral = _blank
    run.grounded = True
    run.marker_point = lambda frame: None if run.signature is None else (0.0, 0.0)
    run.tap_cell = lambda target, before: outcomes.get(
        target.cell, sweep.TapOutcome(sweep.TAP_EMPTY, marker=target.point)
    )
    return run


def test_the_loop_sentences_every_in_bounds_cell_and_then_stops(tmp_path):
    run = build_run(tmp_path, {})

    run.tour()

    assert run.ledger.complete
    assert run.ledger.taps == 0  # tap_cell 被假件接管，計數在它裡面
    assert set(run.ledger.cells_of(sweep.EMPTY)) == {
        (col, row) for col in (2, 3, 4) for row in (4, 5)
    }


def test_a_cell_with_no_feedback_twice_is_left_blank_as_unsure(tmp_path):
    silent = sweep.TapOutcome(sweep.TAP_NONE)
    run = build_run(tmp_path, {(3, 4): silent})

    run.tour()

    assert run.ledger.verdict((3, 4)) == sweep.UNSURE
    assert run.ledger.reasons[(3, 4)] == "no_feedback"
    assert run.ledger.complete


def test_a_card_interrupts_the_window_and_the_cell_is_sentenced_from_the_card(tmp_path):
    run = build_run(tmp_path, {(3, 4): sweep.TapOutcome(sweep.TAP_CARD)})
    seen: list[tuple[int, int]] = []
    run.sentence_card = lambda target: (
        seen.append(target.cell),
        run.ledger.record(target.cell, sweep.ENEMY, name="sig-a"),
    )

    run.tour()

    assert seen == [(3, 4)]
    assert run.ledger.verdict((3, 4)) == sweep.ENEMY
    assert run.ledger.complete


def test_the_tap_fuse_stops_the_loop_before_the_ledger_is_complete(tmp_path):
    run = build_run(tmp_path, {})
    run.max_taps = 0

    run.tour()

    assert not run.ledger.complete
    assert run.ledger.pending()


def marked_run(tmp_path, sightings: list[bool]) -> SweepRun:
    """節點擴張的離線骨架：把「推鏡後看不看得到標記」寫成一串答案。"""
    run = build_run(tmp_path, {})
    run.signature = object()
    run.marker_cell = (3, 4)
    run.offset = (0.0, 0.0)
    run.walk = sweep.NodeWalk(full_reach=200.0)
    run.carry_marker = lambda direction, frame: None
    run.stride = lambda direction: run.walk.reach
    run.zero = lambda: run.walk.rooted()
    run.legs = []
    run.pan = lambda direction, frame, reach=None: (
        run.legs.append((direction, reach)),
        (reach, _blank()),
    )[1]
    answers = list(sightings)
    run.anchor_on_marker = lambda: (
        sweep.TrustNode(cell=run.marker_cell, offset=run.offset)
        if answers.pop(0)
        else None
    )
    return run


def test_an_expansion_that_finds_the_marker_registers_a_new_node(tmp_path):
    run = marked_run(tmp_path, [True])

    run.expand("east")

    assert [node.cell for node in run.walk.nodes] == [(3, 4)]
    assert run.legs == [("east", 200.0)]


def test_a_lost_marker_retreats_the_same_amount_and_retries_at_half_stride(tmp_path):
    run = marked_run(tmp_path, [False, True, True])

    run.expand("east")

    assert run.legs == [("east", 200.0), ("west", 200.0), ("east", 100.0)]
    assert run.walk.failures == 0  # 半步幅那一把成功了，這個節點的敗績歸零
    assert len(run.walk.nodes) == 1


def test_two_failures_on_the_same_node_fall_back_to_the_corner(tmp_path):
    run = marked_run(tmp_path, [False, True, False, True])

    run.expand("east")

    assert run.legs == [
        ("east", 200.0),
        ("west", 200.0),
        ("east", 100.0),
        ("west", 100.0),
    ]
    assert run.walk.nodes == []


def test_losing_the_marker_on_the_way_back_keeps_retreating_down_the_chain(tmp_path):
    run = marked_run(tmp_path, [False, False, False])
    run.walk.expanded(sweep.TrustNode(cell=(1, 4), offset=(0.0, 0.0)))

    run.expand("east")

    assert run.legs == [("east", 200.0), ("west", 200.0), ("west", 200.0)]
    assert run.walk.nodes == []


def test_the_stride_never_pushes_the_marker_out_of_the_next_window(tmp_path):
    run = build_run(tmp_path, {})
    run.marker_cell = (3, 4)
    run.offset = (0.0, 0.0)
    run.walk = sweep.NodeWalk(full_reach=board.PAN_MAX_REACH)

    reach = run.stride("east")

    point = sweep.screen_of(GRID, (3, 4), (0.0, 0.0))
    room = sweep.stride_cap(point, "east", margin=sweep.MARKER_KEEP_PITCH * GRID.col_pitch)
    assert reach == max(board.PAN_MIN_REACH, min(board.PAN_MAX_REACH, room))


def test_the_loop_refuses_to_tap_a_cell_while_the_camera_is_lost(tmp_path):
    run = build_run(tmp_path, {})
    run.tap_cell = SweepRun.tap_cell.__get__(run)
    run.fix.lose()

    with pytest.raises(sweep.Adrift):
        run.tap_cell(sweep.TapTarget((2, 4), (100.0, 100.0)), _blank())


def test_a_lost_camera_re_anchors_at_the_corner_before_any_clearing_resumes(tmp_path):
    run = build_run(tmp_path, {})
    run.fix.lose()
    homed: list[bool] = []
    run.zero = lambda: run.fix.regain()
    run.home = lambda: homed.append(True)

    run.tour()

    assert homed == [True]
    assert run.ledger.complete


def swiping_run(tmp_path) -> SweepRun:
    """推鏡的相位驗收骨架：手勢與解鎖呼叫全部記下來，不碰任何裝置。"""
    run = build_run(tmp_path, {})
    run.ledger = None  # 到邊判準不介入，這裡量的是純「被吃」鏈
    run.swipes = []
    run.unlocks = []
    run.device = SimpleNamespace(
        tap=lambda x, y: None,
        swipe=lambda *args: run.swipes.append(args),
        ensure_unlocked=lambda force=False: run.unlocks.append(force),
    )
    return run


def test_an_eaten_gesture_is_unlocked_and_resent_unchanged(tmp_path, monkeypatch):
    run = swiping_run(tmp_path)
    reads = iter([
        ((0.0, 0.0), (80.0, 80.0)),  # 推之前
        ((0.0, 0.0), (80.0, 80.0)),  # 推之後：相位沒動＝被吃
        ((40.0, 0.0), (80.0, 80.0)),  # 重發之後：動了
    ])
    monkeypatch.setattr(board, "lattice_phase", lambda frame: next(reads))
    monkeypatch.setattr(board, "find_sightings", lambda frame: ())

    stroke, _ = SweepRun.pan(run, "east", _blank(), 200.0)

    assert stroke == 200.0
    assert len(run.swipes) == 2
    assert run.swipes[0] == run.swipes[1]  # 原手勢原樣重發
    assert run.unlocks == [True]


def test_a_gesture_eaten_every_time_halts_instead_of_spinning(tmp_path, monkeypatch):
    run = swiping_run(tmp_path)
    monkeypatch.setattr(board, "lattice_phase", lambda frame: ((0.0, 0.0), (80.0, 80.0)))
    monkeypatch.setattr(board, "find_sightings", lambda frame: ())

    with pytest.raises(Halt):
        SweepRun.pan(run, "east", _blank(), 200.0)

    assert len(run.swipes) == sweep.GESTURE_EATEN_LIMIT


def test_pushing_past_a_visible_border_is_exhaustion_not_an_eaten_gesture(
    tmp_path, monkeypatch
):
    run = swiping_run(tmp_path)
    monkeypatch.setattr(board, "lattice_phase", lambda frame: ((0.0, 0.0), (90.0, 90.0)))
    monkeypatch.setattr(board, "find_sightings", lambda frame: ())
    monkeypatch.setattr(sweep, "read_borders", lambda frame: {"north": 120.0})

    stroke, _ = SweepRun.pan(run, "north", _blank(), 200.0)

    assert stroke == 0.0
    assert len(run.swipes) == 1  # 不重發、不 Halt
    assert run.unlocks == []


def test_a_border_already_in_the_ledger_ends_the_push_without_seeing_it(
    tmp_path, monkeypatch
):
    run = swiping_run(tmp_path)
    run.ledger = sweep.SweepLedger(grid=GRID)
    run.ledger.boundary["north"] = 2  # 鏡位 (0,0) 的窗最北就是第 2 列
    run.offset = (0.0, 0.0)
    run.witness = lambda frame: None
    monkeypatch.setattr(board, "lattice_phase", lambda frame: ((0.0, 0.0), (90.0, 90.0)))
    monkeypatch.setattr(board, "find_sightings", lambda frame: ())
    monkeypatch.setattr(sweep, "read_borders", lambda frame: {})

    stroke, _ = SweepRun.pan(run, "north", _blank(), 200.0)

    assert stroke == 0.0
    assert len(run.swipes) == 1


def test_homing_walks_one_station_per_screen_and_never_re_clears_a_cell(tmp_path):
    run = build_run(tmp_path, {})
    run.signature = object()
    run.marker_cell = (2, 4)
    run.offset = (0.0, 0.0)
    run.ledger.boundary.update(west=2, east=40, north=4, south=4)
    for col in range(2, 40):
        run.ledger.record((col, 4), sweep.EMPTY)  # 鋒面在 (40,4)，一路都已裁決
    run.legs = []
    run.carried = []
    run.pan = lambda direction, frame, reach=None: (run.legs.append(direction), (0.0, _blank()))[1]
    run.stride = lambda direction: 200.0
    run.carry_marker = lambda direction, frame: run.carried.append(direction)
    run.anchor_on_marker = lambda: sweep.TrustNode(cell=run.marker_cell, offset=run.offset)

    before = dict(run.ledger.state)
    run.home()

    assert run.legs == run.carried
    assert run.legs and set(run.legs) == {"east"}
    assert run.ledger.state == before  # 返航不重掃：帳本一格都沒動


def test_homing_that_never_reaches_the_frontier_halts_instead_of_looping(tmp_path):
    run = build_run(tmp_path, {})
    run.zero = lambda: run.fix.regain()
    run.home = lambda: run.fix.lose()
    run.fix.lose()

    with pytest.raises(Halt):
        run.tour()


def test_zeroing_reads_the_borders_off_the_pan_verdict_frame_instead_of_reshooting(
    tmp_path, monkeypatch
):
    """一張截圖實機要 ~2.4s；驗收幀比重跑一次 settled() 的第一張還晚，重拍純浪費
    （0804 那輪 zero 段 24 張裡 16 張是這樣花掉的）。逐把不重拍，只有寫世界座標
    前的那一次角落複驗另拍一幀。"""
    run = build_run(tmp_path, {})
    run.ledger = None
    shots = []
    run.settled = lambda: (shots.append("settled"), _blank())[1]
    legs = []
    run.pan = lambda direction, frame, reach=None: (legs.append(direction), (0.0, _blank()))[1]
    borders = iter(
        [{}, {"west": 1.0}, {"west": 1.0, "north": 2.0}, {"west": 1.0, "north": 2.0}]
    )
    monkeypatch.setattr(sweep, "read_borders", lambda frame: next(borders))
    monkeypatch.setattr(board, "find_lattice", lambda frame: GRID)
    monkeypatch.setattr(sweep, "anchor_northwest", lambda lattice, seen: (GRID, (0.0, 0.0)))

    run.zero()

    assert legs == ["west", "north"]
    assert shots == ["settled", "settled"]


def filtered_run(tmp_path, candidates, outcomes=None):
    run = build_run(tmp_path, outcomes or {})
    run.filter_mode = sweep.FILTER_CANDIDATES
    run.candidates = lambda frame: frozenset(candidates)
    return run


def test_the_filter_only_taps_candidates_and_books_the_rest_as_inferred_empty(tmp_path):
    run = filtered_run(tmp_path, {(3, 4)})
    tapped: list[tuple[int, int]] = []
    run.tap_cell = lambda target, before: (
        tapped.append(target.cell),
        sweep.TapOutcome(sweep.TAP_EMPTY, marker=target.point),
    )[1]

    run.tour()

    assert tapped == [(3, 4)]
    assert run.ledger.verdict((3, 4)) == sweep.EMPTY
    assert run.ledger.verdict((2, 4)) == sweep.EMPTY_INFERRED
    assert run.ledger.reasons[(2, 4)] == "candidate_filter"
    assert run.ledger.complete


def test_the_filter_falls_back_to_tapping_every_cell_when_the_grid_is_unreadable(tmp_path):
    run = build_run(tmp_path, {})
    run.filter_mode = sweep.FILTER_CANDIDATES

    run.tour()  # 合成幀讀不出格線 → candidates() 回 None

    assert not run.ledger.cells_of(sweep.EMPTY_INFERRED)
    assert len(run.ledger.cells_of(sweep.EMPTY)) == 6


def test_a_card_under_an_inferred_empty_rewrites_the_ledger_with_the_click(tmp_path):
    run = filtered_run(tmp_path, set())
    run.ledger.record((3, 4), sweep.EMPTY_INFERRED, reason="candidate_filter")
    run.tap_cell = lambda target, before: sweep.TapOutcome(sweep.TAP_CARD)
    run.sentence_card = lambda target: run.ledger.record(target.cell, sweep.ENEMY)
    run.marker_cell = (2, 4)
    run.signature = object()

    run.carry_marker("east", _blank())

    assert run.ledger.verdict((3, 4)) == sweep.ENEMY
    assert run.marker_cell == (2, 4)


def pinning_run(tmp_path, monkeypatch, marks: list[tuple[float, float]]) -> SweepRun:
    """夾停骨架：相位永遠不動，標記位移由 marks 逐幀給。"""
    run = swiping_run(tmp_path)
    run.signature = object()
    run.marker_point = SweepRun.marker_point.__get__(run)
    monkeypatch.setattr(board, "lattice_phase", lambda frame: ((0.0, 0.0), (100.0, 100.0)))
    monkeypatch.setattr(board, "find_sightings", lambda frame: ())
    monkeypatch.setattr(sweep, "read_borders", lambda frame: {})
    points = iter(marks)
    monkeypatch.setattr(board, "find_marker", lambda frame, sig, **kw: next(points))
    return run


def test_a_full_stroke_the_phase_could_not_see_is_still_a_landed_gesture(
    tmp_path, monkeypatch
):
    run = pinning_run(tmp_path, monkeypatch, [(1400.0, 800.0), (1400.0, 550.0)])

    stroke, _ = SweepRun.pan(run, "south", _blank(), 260.0)

    assert stroke == 260.0
    assert len(run.swipes) == 1
    assert run.pinned == set()


def test_a_pinned_camera_turns_instead_of_halting_and_writes_no_border(
    tmp_path, monkeypatch
):
    marks = [(1400.0, 800.0), (1400.0, 806.0)] * sweep.GESTURE_PINNED_LIMIT
    run = pinning_run(tmp_path, monkeypatch, marks)

    stroke, _ = SweepRun.pan(run, "south", _blank(), 260.0)

    assert stroke == 0.0
    assert run.pinned == {"south"}
    assert run.unlocks == []  # 夾停不是被吃，不做解鎖重發
    assert len(run.swipes) == sweep.GESTURE_PINNED_LIMIT


def test_a_vertical_push_is_shortened_so_the_row_pitch_cannot_hide_it(
    tmp_path, monkeypatch
):
    """0805-031635 的 Halt：row_pitch 85 上推滿 260，相位殘量落回 0 附近＝真的走了
    卻讀成被吃，重發到 Halt。行程先讓路給相位，這條鏈才判得出來。"""
    run = swiping_run(tmp_path)
    reads = iter([((0.0, 0.0), (90.5, 85.0)), ((0.0, -27.0), (90.5, 85.0))])
    monkeypatch.setattr(board, "lattice_phase", lambda frame: next(reads))
    monkeypatch.setattr(board, "find_sightings", lambda frame: ())

    stroke, _ = SweepRun.pan(run, "north", _blank(), 260.0)

    assert stroke < 260.0
    assert abs(board._wrap_phase(board.PAN_GAIN * stroke, 85.0)) >= board.PHASE_LEGIBLE_MARGIN
    x1, y1, _, y2 = run.swipes[0][:4]
    assert y2 - y1 == round(stroke)  # 手勢真的照縮過的行程打出去


def test_a_carry_tap_with_no_fill_is_retried_and_never_moves_the_marker_cell(tmp_path):
    silent = sweep.TapOutcome(sweep.TAP_NONE)
    run = build_run(tmp_path, {})
    run.signature = object()
    run.marker_cell = (2, 4)
    run.ledger.record((3, 4), sweep.EMPTY)
    taps: list[tuple[int, int]] = []
    run.tap_cell = lambda target, before: (taps.append(target.cell), silent)[1]

    assert not SweepRun.carry_marker(run, "east", _blank())
    assert taps == [(3, 4), (3, 4)]
    assert run.marker_cell == (2, 4)


def test_a_marker_that_vanished_is_replanted_before_the_camera_is_pushed(tmp_path):
    """窗內看不到填色就當標記沒了：不准把「幾何上在窗內」當成推鏡後有證人。"""
    run = build_run(tmp_path, {})
    run.signature = object()
    run.marker_cell = (4, 4)  # 前緣格，舊行為在這裡會判定不用搬
    run.ledger.record((4, 4), sweep.EMPTY)
    run.marker_point = lambda frame: None
    taps: list[tuple[int, int]] = []
    run.tap_cell = lambda target, before: (
        taps.append(target.cell),
        sweep.TapOutcome(sweep.TAP_EMPTY, marker=target.point),
    )[1]

    assert SweepRun.carry_marker(run, "east", _blank())
    assert taps == [(4, 4)]
    assert run.marker_cell == (4, 4)


def test_a_root_recovery_inside_an_expansion_counts_towards_the_stranding_fuse(tmp_path):
    """expand 自己走的 zero＋home 也會把錨補回來，計數不掛在這裡就永遠是 0
    （20260805-144856：十五圈原地空轉一次都沒攔到）。"""
    run = marked_run(tmp_path, [False] * 40)
    run.home = lambda: None

    with pytest.raises(Halt):
        for _ in range(STRANDINGS_LIMIT + 2):
            run.expand("east")


def test_a_corner_whose_second_reading_disagrees_never_writes_the_world(
    tmp_path, monkeypatch
):
    run = build_run(tmp_path, {})
    run.landmarks = {"west": 0.0, "north": 0.0}
    seen = iter([{"west": 100.0, "north": north} for north in (200.0, 500.0) * 4])
    monkeypatch.setattr(sweep, "read_borders", lambda frame: next(seen))

    with pytest.raises(Halt):
        run.zero()

    assert run.offset == (0.0, 0.0)  # 對不上的讀數一格都不寫進鏡位


def test_a_corner_confirmed_by_a_second_frame_rezeroes_from_that_reading(
    tmp_path, monkeypatch
):
    run = build_run(tmp_path, {})
    run.landmarks = {"west": 0.0, "north": 0.0}
    seen = iter([{"west": 100.0, "north": 200.0}, {"west": 104.0, "north": 206.0}])
    monkeypatch.setattr(sweep, "read_borders", lambda frame: next(seen))

    run.zero()

    assert run.offset == (-104.0, -206.0)


def test_a_centre_anchor_taps_nothing_until_a_strong_witness_backs_it(tmp_path):
    run = build_run(tmp_path, {})
    run.grounded = False
    run.confirm = lambda: False
    tapped: list[tuple[int, int]] = []
    run.tap_cell = lambda target, before: (tapped.append(target.cell), None)[1]
    run.zero = lambda: run.fix.regain()
    run.home = lambda: run.fix.lose()

    with pytest.raises(Halt):  # 一直背書不了＝失位，走既有回退直到停手
        run.tour()

    assert tapped == []


def test_a_backed_anchor_resumes_the_clearing(tmp_path):
    run = build_run(tmp_path, {})
    run.grounded = False
    backed = []

    def confirm() -> bool:
        backed.append(True)
        run.grounded = True
        return True

    run.confirm = confirm

    run.tour()

    assert backed == [True]
    assert run.ledger.complete


def test_a_second_ungrounded_anchor_in_a_row_is_treated_as_lost(tmp_path, monkeypatch):
    run = build_run(tmp_path, {})
    run.marker_cell = None
    monkeypatch.setattr(sweep, "read_borders", lambda frame: {})
    monkeypatch.setattr(
        sweep, "reanchor", lambda grid, **kw: ((5.0, 5.0), sweep.SOURCE_CENTRE)
    )

    SweepRun.relocate(run, candidate=(5.0, 5.0))
    assert run.fix.anchored and not run.grounded  # 置中反推那一步照舊

    assert not SweepRun.confirm(run)
    assert not run.fix.anchored  # 背書不了的下一步就當失位


def test_a_marker_backed_anchor_clears_the_ungrounded_streak(tmp_path, monkeypatch):
    run = build_run(tmp_path, {})
    run.grounded = False
    run.ungrounded = 1
    run.signature = object()
    run.marker_cell = (2, 4)
    monkeypatch.setattr(sweep, "read_borders", lambda frame: {})
    monkeypatch.setattr(board, "find_marker", lambda frame, sig, **kw: (100.0, 100.0))

    assert SweepRun.confirm(run)
    assert run.grounded and run.ungrounded == 0
    assert run.offset == (GRID.centre_of((2, 4))[0] - 100.0, GRID.centre_of((2, 4))[1] - 100.0)


def test_the_window_frame_is_taken_only_after_the_hub_is_neutral(tmp_path, monkeypatch):
    run = build_run(tmp_path, {})
    del run.neutral
    views = iter([False, True])
    escapes: list[bool] = []
    run.on_hub = lambda frame=None: next(views)
    run.escape = lambda: escapes.append(True)
    monkeypatch.setattr("scripts.sweep_scan._card_present", lambda frame: False)

    SweepRun.neutral(run)

    assert escapes == [True]


def test_a_unit_card_still_up_is_escaped_before_the_window_frame(tmp_path, monkeypatch):
    run = build_run(tmp_path, {})
    del run.neutral
    cards = iter([True, False])
    escapes: list[bool] = []
    run.escape = lambda: escapes.append(True)
    monkeypatch.setattr("scripts.sweep_scan._card_present", lambda frame: next(cards))

    SweepRun.neutral(run)

    assert escapes == [True]


def witnessing_run(tmp_path):
    run = build_run(tmp_path, {})
    del run.witness  # build_run 把 witness 換成假件，這幾支要試的正是它
    run.offset = (10.0, 0.0)
    return run


def test_an_inferred_camera_may_not_open_a_new_landmark(tmp_path, monkeypatch):
    run = witnessing_run(tmp_path)
    monkeypatch.setattr(sweep, "read_borders", lambda frame: {"east": 100.0})

    run.grounded = False
    for _ in range(sweep.LANDMARK_VOTES + 2):
        run.witness(_blank())

    assert run.landmarks == {}
    assert run.sightings == {}


def test_a_landmark_needs_several_sightings_that_agree_with_each_other(
    tmp_path, monkeypatch
):
    run = witnessing_run(tmp_path)
    run.grounded = True
    run.ledger.boundary.pop("east")
    seen = [100.0, 900.0, 100.0, 100.0, 100.0]
    monkeypatch.setattr(sweep, "read_borders", lambda frame: {"east": seen.pop(0)})

    for _ in range(3):
        run.witness(_blank())
    assert run.landmarks == {}  # 三次目擊裡有一次對不上，不升格

    for _ in range(2):
        run.witness(_blank())
    assert run.landmarks == {"east": 110.0}
    assert run.ledger.boundary["east"] == sweep.border_cell(run.ledger.grid, "east", 110.0)


def test_a_side_that_keeps_contradicting_with_one_voice_unseats_the_landmark(tmp_path):
    run = build_run(tmp_path, {})
    run.signature = object()
    run.marker_cell = (2, 2)
    run.landmarks = {"east": 500.0}  # 一次寫死的髒地標
    run.ledger.boundary.pop("east")
    board_find = board.find_marker
    try:
        board.find_marker = lambda frame, signature, region=None, holes=(): (100.0, 100.0)
        sweep_borders = sweep.read_borders
        sweep.read_borders = lambda frame: {"east": 1000.0}
        nodes = [run.anchor_on_marker() for _ in range(sweep.LANDMARK_REVOKE_CLASHES)]
    finally:
        board.find_marker = board_find
        sweep.read_borders = sweep_borders

    assert nodes[:-1] == [None] * (sweep.LANDMARK_REVOKE_CLASHES - 1)
    assert nodes[-1] is not None  # 第 N 次一致的反證翻案，擴張就地接回去
    assert run.landmarks["east"] == 1150.0
    assert run.offset == (150.0, 150.0)
