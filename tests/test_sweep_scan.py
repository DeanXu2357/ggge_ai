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
from scripts.sweep_scan import (
    FEEDBACK_POLL_S,
    FEEDBACK_WAIT_S,
    SETTLE_POLL_S,
    SETTLE_STABLE_DIFF,
    SETTLE_WAIT_S,
    STRANDINGS_LIMIT,
    Halt,
    SweepRun,
    frame_motion,
    load_target,
)

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


def real_tap_run(tmp_path, verdicts: list[str]) -> tuple[SweepRun, list[float], list[float]]:
    """真的 tap_cell＋假時鐘：裁決結果寫成一串答案，睡多久記在流水上。"""
    run = build_run(tmp_path, {})
    run.tap_cell = SweepRun.tap_cell.__get__(run)
    naps: list[float] = []
    now = [0.0]
    run.sleep = lambda seconds: (naps.append(seconds), now.__setitem__(0, now[0] + seconds))[0]
    run.clock = lambda: now[0]
    answers = iter(verdicts)
    run.classify = lambda *args, **kwargs: sweep.TapOutcome(next(answers, verdicts[-1]))
    return run, naps, now


def test_the_tap_polls_until_the_feedback_shows_up(tmp_path):
    run, naps, now = real_tap_run(
        tmp_path, [sweep.TAP_NONE, sweep.TAP_NONE, sweep.TAP_EMPTY]
    )

    outcome = run.tap_cell(sweep.TapTarget((2, 4), (100.0, 100.0)), _blank())

    assert outcome.verdict == sweep.TAP_EMPTY
    assert naps == [run.tap_interval, FEEDBACK_POLL_S, FEEDBACK_POLL_S]
    assert now[0] < FEEDBACK_WAIT_S


def test_the_tap_gives_up_on_feedback_at_the_deadline(tmp_path):
    run, naps, now = real_tap_run(tmp_path, [sweep.TAP_NONE])

    outcome = run.tap_cell(sweep.TapTarget((2, 4), (100.0, 100.0)), _blank())

    assert outcome.verdict == sweep.TAP_NONE
    assert now[0] >= FEEDBACK_WAIT_S
    assert sum(naps) == pytest.approx(now[0])


def _stirred(pixels: int) -> np.ndarray:
    """在全黑幀上點亮一片：與 _blank() 相比就有 `pixels` 個「明顯變了」的像素。"""
    frame = _blank()
    frame.reshape(-1, 3)[:pixels] = 255
    return frame


def settle_run(tmp_path, frames: list[np.ndarray]) -> tuple[SweepRun, list[float], list[float]]:
    """真的 settled()＋假時鐘：幀序列排好，最後一張耗盡就一直回它。"""
    run = build_run(tmp_path, {})
    del run.settled
    served = iter(frames)
    run.camera = SimpleNamespace(grab=lambda: next(served, frames[-1]), keep=lambda label: None)
    naps: list[float] = []
    now = [0.0]
    run.sleep = lambda seconds: (naps.append(seconds), now.__setitem__(0, now[0] + seconds))[0]
    run.clock = lambda: now[0]
    return run, naps, now


def test_the_settle_waits_for_the_glide_to_stop_before_it_hands_back_a_frame(tmp_path):
    landed = _stirred(200_003)  # 與前一幀只差 3 px：待機動畫等級的殘動
    run, naps, now = settle_run(
        tmp_path, [_blank(), _stirred(100_000), _stirred(200_000), landed]
    )

    frame = run.settled()

    assert frame is landed
    assert naps == [SETTLE_POLL_S] * 3
    assert now[0] < SETTLE_WAIT_S


def test_a_frame_that_never_goes_quiet_is_handed_back_at_the_deadline(tmp_path):
    stirring = [_blank(), _stirred(100_000)] * 20
    run, naps, now = settle_run(tmp_path, stirring)

    frame = run.settled()

    assert frame.shape == _blank().shape
    assert now[0] >= SETTLE_WAIT_S
    assert naps == [SETTLE_POLL_S] * int(SETTLE_WAIT_S / SETTLE_POLL_S)


def test_a_screen_that_is_already_still_costs_one_poll(tmp_path):
    run, naps, now = settle_run(tmp_path, [_blank(), _blank()])

    run.settled()

    assert naps == [SETTLE_POLL_S]
    assert now[0] == SETTLE_POLL_S


def test_a_camera_sliding_moves_far_more_pixels_than_the_stable_threshold():
    rng = np.random.default_rng(0)
    still = _blank()
    still[300:800, 400:1400] = rng.integers(0, 256, (500, 1000, 3), dtype=np.uint8)
    idle = still.copy()
    idle[500:520, 600:620] = 255  # 一隻精靈的待機動畫
    slid = np.roll(still, 60, axis=1)  # 鏡頭滑一段

    assert frame_motion(still, idle) < SETTLE_STABLE_DIFF
    assert frame_motion(still, slid) > SETTLE_STABLE_DIFF * 10


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


def drifting_run(tmp_path, found):
    run = build_run(tmp_path, {})
    run.signature = object()
    run.baseline = (500.0, 500.0)
    run.grounded = True
    run.marker_point = lambda frame: found
    return run


def test_an_integer_cell_drift_is_caught_even_though_the_phase_gate_is_blind(tmp_path):
    run = drifting_run(tmp_path, None)
    board_find = board.find_marker
    try:
        # 整整一格的漂移：相位取模後是 0，相位閘一輩子看不見。
        board.find_marker = lambda frame, signature, region=None, holes=(): (600.0, 500.0)
        steady = run.steady(_blank())
    finally:
        board.find_marker = board_find

    assert run.aimed(_blank())  # 第二道閘讀不出格線就放行——盲區實證
    assert not steady
    assert not run.grounded


def test_a_marker_the_search_window_cannot_find_falls_back_to_the_phase_gate(tmp_path):
    run = drifting_run(tmp_path, None)
    board_find = board.find_marker
    try:
        board.find_marker = lambda frame, signature, region=None, holes=(): None
        steady = run.steady(_blank())
    finally:
        board.find_marker = board_find

    assert steady
    assert run.grounded


def test_the_window_baseline_follows_the_marker_cell_by_cell(tmp_path):
    run = build_run(tmp_path, {})
    run.signature = object()
    run.baseline = (500.0, 500.0)
    target = sweep.TapTarget((3, 4), (250.0, 450.0))
    run.tap_cell = lambda tapped, before: sweep.TapOutcome(
        sweep.TAP_EMPTY, marker=tapped.point
    )

    assert run.decide(target, _blank()) == sweep.TAP_EMPTY
    assert run.baseline == (250.0, 450.0)


def test_a_drifted_window_stops_tapping_and_leaves_the_cell_unsentenced(tmp_path):
    run = build_run(tmp_path, {})
    run.signature = object()
    run.baseline = (500.0, 500.0)
    plan = sweep.plan_window(run.ledger, (0.0, 0.0), heading="east")
    board_find = board.find_marker
    try:
        board.find_marker = lambda frame, signature, region=None, holes=(): (600.0, 500.0)
        interrupted = run.work(plan, _blank())
    finally:
        board.find_marker = board_find

    assert interrupted
    assert not run.grounded
    assert run.ledger.cells_of(sweep.EMPTY) == ()


def test_the_constellation_takes_over_when_the_marker_is_gone_and_the_edges_are_mute(tmp_path):
    run = build_run(tmp_path, {})
    del run.relocate
    for index, cell in enumerate(((3, 2), (6, 3), (9, 2), (4, 6), (8, 7))):
        run.ledger.record(cell, sweep.ENEMY, name=f"sig-{index}")
    truth = (200.0, 100.0)
    peaks = tuple(
        (GRID.centre_of(cell)[0] - truth[0], GRID.centre_of(cell)[1] - truth[1])
        for cell in sweep.identified_units(run.ledger)
    )
    board_units = board.find_unit_screen_hints
    try:
        board.find_unit_screen_hints = lambda frame, *args, **kwargs: peaks
        run.relocate()
    finally:
        board.find_unit_screen_hints = board_units

    assert run.offset == pytest.approx(truth)
    # 星座是假說級：grounded 維持 False，下一步得靠 confirm() 拿強證人背書。
    assert not run.grounded


def roster_run(tmp_path, candidates, outcomes=None, counter=(0, 1)):
    run = filtered_run(tmp_path, candidates, outcomes)
    run.filter_mode = sweep.FILTER_ROSTER
    run.target = sweep.Census(enemies=counter[1], allies=0, npcs=0) if counter else None
    run.kill_counter = lambda frame: counter
    run.roster_check = lambda: True
    return run


def test_the_kill_counter_denominator_is_read_and_must_agree_with_the_truth(tmp_path):
    run = roster_run(tmp_path, set(), counter=(3, 18))

    run.take_census()

    assert run.enemy_total == 18
    assert run.target == sweep.Census(18, 0, 0)


def test_a_kill_counter_that_disagrees_with_the_truth_file_cancels_the_early_close(tmp_path):
    run = roster_run(tmp_path, set(), counter=(3, 18))
    run.target = sweep.Census(enemies=17, allies=0, npcs=0)

    run.take_census()

    assert run.target is None


def test_a_stage_without_a_truth_file_taps_every_candidate_instead_of_closing(tmp_path):
    run = roster_run(tmp_path, set(), counter=None)
    run.take_census()

    run.tour()

    assert run.target is None
    assert not run.closed
    # 早收條件不成立就是照舊掃：每一格都收到裁決
    assert run.ledger.complete


def test_a_closed_census_exempts_the_rest_of_the_board_without_tapping_it(tmp_path):
    run = roster_run(tmp_path, set())
    run.target = sweep.Census(1, 0, 0)
    run.ledger.record((3, 4), sweep.ENEMY, name="a")

    assert run.close_census()

    assert run.closed
    assert run.ledger.verdict((2, 5)) == sweep.EMPTY_INFERRED
    assert run.ledger.reasons[(2, 5)] == sweep.CENSUS_CLOSED
    assert run.ledger.complete


def test_an_open_census_exempts_nothing(tmp_path):
    run = roster_run(tmp_path, set())
    run.target = sweep.Census(2, 0, 0)
    run.ledger.record((3, 4), sweep.ENEMY, name="a")

    assert not run.close_census()
    assert not run.ledger.cells_of(sweep.EMPTY_INFERRED)


def test_a_roster_check_that_cannot_see_a_booked_unit_keeps_the_sweep_going(tmp_path):
    run = roster_run(tmp_path, {(3, 4)})
    checks: list[bool] = []

    def check() -> bool:
        checks.append(True)
        return False

    run.roster_check = check
    run.tap_cell = lambda target, before: (
        sweep.TapOutcome(sweep.TAP_CARD)
        if target.cell == (3, 4)
        else sweep.TapOutcome(sweep.TAP_EMPTY, marker=target.point)
    )
    run.sentence_card = lambda target: run.ledger.record(target.cell, sweep.ENEMY)
    run.candidates = lambda frame: frozenset(run.ledger.pending())

    run.tour()

    assert checks
    assert not run.closed
    assert not run.ledger.cells_of(sweep.EMPTY_INFERRED)


def test_the_window_plan_is_handed_the_peak_ranking(tmp_path, monkeypatch):
    run = build_run(tmp_path, {})
    run.filter_mode = sweep.FILTER_CANDIDATES
    monkeypatch.setattr(board, "find_lattice", lambda frame: True)
    monkeypatch.setattr(board, "lattice_phase", lambda frame: None)
    monkeypatch.setattr(sweep, "candidate_points", lambda frame: ((350.0, 450.0), (150.0, 450.0)))
    orders: list[dict] = []
    plan_window = sweep.plan_window
    monkeypatch.setattr(
        sweep,
        "plan_window",
        lambda *args, order=None, **kw: (orders.append(order), plan_window(*args, **kw))[1],
    )

    cells = run.candidates(_blank())

    assert (3, 4) in cells
    assert run.ranking[(3, 4)] == 0
    # 弱峰獨佔的格排在強峰之後
    assert run.ranking[(1, 4)] == 1

    run.tour()

    assert orders and orders[0] is run.ranking


def test_a_cell_seen_again_takes_its_inferred_empty_back_and_is_tapped(tmp_path):
    run = filtered_run(tmp_path, {(3, 4)})
    run.ledger.record((3, 4), sweep.EMPTY_INFERRED, reason="candidate_filter")
    run.inferred_at[(3, 4)] = 7
    tapped: list[tuple[int, int]] = []
    run.tap_cell = lambda target, before: (
        tapped.append(target.cell),
        sweep.TapOutcome(sweep.TAP_SHIFTED),
    )[1]
    run.sentence_shift = lambda target, outcome: run.ledger.record(target.cell, sweep.ALLY)

    run.tour()

    assert (3, 4) in tapped
    assert run.ledger.verdict((3, 4)) == sweep.ALLY
    retracted = [
        entry for entry in _entries(run) if entry["kind"] == "inference_retracted"
    ]
    assert retracted[0]["cell"] == [3, 4]
    assert retracted[0]["inferred_at"] == 7


def _entries(run) -> list[dict]:
    import json

    return [json.loads(line) for line in run.journal.path.read_text().splitlines()]


def test_a_card_that_does_not_dock_on_the_enemy_side_is_booked_as_a_third_party(tmp_path):
    from ggge_ai.battle.state import Faction

    run = build_run(tmp_path, {})
    run.identifier = SimpleNamespace(
        identify=lambda frame: SimpleNamespace(faction=Faction.ALLY, side="right")
    )

    run.sentence_card(sweep.TapTarget((3, 4), (350.0, 450.0)))

    assert run.ledger.verdict((3, 4)) == sweep.NPC
    assert run.ledger.reasons[(3, 4)] == "right"


def test_the_truth_file_supplies_the_closing_target(tmp_path):
    import json

    root = tmp_path / "truth"
    root.mkdir()
    (root / "uc_x.json").write_text(
        json.dumps({"enemy_count": 18, "npc_count": 0}), encoding="utf-8"
    )
    journal = Journal(tmp_path / "sweep.jsonl")

    assert load_target("uc_x", 10, journal, root) == sweep.Census(18, 10, 0)
    # 我方台數屬出擊配置：檔案沒寫、CLI 也沒給就不早收
    assert load_target("uc_x", None, journal, root) is None
    # 首刷：沒有真值檔一律不早收
    assert load_target("uc_new", 10, journal, root) is None
    assert load_target(None, 10, journal, root) is None


def test_a_truth_file_without_a_third_party_count_does_not_close(tmp_path):
    import json

    root = tmp_path / "truth"
    root.mkdir()
    (root / "uc_x.json").write_text(json.dumps({"enemy_count": 18}), encoding="utf-8")
    journal = Journal(tmp_path / "sweep.jsonl")

    assert load_target("uc_x", 10, journal, root) is None


def test_a_candidate_on_an_exempted_cell_fails_the_roster_check(tmp_path, monkeypatch):
    run = roster_run(tmp_path, set())
    run.roster_check = SweepRun.roster_check.__get__(run)
    run.ledger.record((3, 4), sweep.EMPTY_INFERRED, reason=sweep.CENSUS_CLOSED)
    run.inferred_at[(3, 4)] = 11
    monkeypatch.setattr(sweep, "candidate_points", lambda frame: ((350.0, 450.0),))

    assert not run.roster_check()

    assert run.ledger.verdict((3, 4)) == sweep.UNKNOWN
    retracted = [e for e in _entries(run) if e["kind"] == "inference_retracted"]
    assert retracted[0]["cell"] == [3, 4]
    assert retracted[0]["reason"] == "roster_check"
    # 帳本自己沒有虛帳，所以這一次不算總驗失敗次數
    assert run.roster_failures == 0


def test_two_failed_roster_checks_close_the_early_exit_for_good(tmp_path, monkeypatch):
    run = roster_run(tmp_path, set())
    run.roster_check = SweepRun.roster_check.__get__(run)
    run.ledger.record((3, 4), sweep.ENEMY, name="a")
    monkeypatch.setattr(sweep, "candidate_points", lambda frame: ())

    assert not run.roster_check()
    assert run.target is not None

    assert not run.roster_check()
    assert run.target is None
