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
from scripts.sweep_scan import Halt, SweepRun

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
    run.pan = lambda direction, frame, reach=None: reach or 0.0
    run.relocate = lambda candidate=None: None
    run.escape = lambda: None
    run.on_hub = lambda: True
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
        reach,
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
        ((0.0, 0.0), (90.0, 90.0)),  # 推之前
        ((0.0, 0.0), (90.0, 90.0)),  # 推之後：相位沒動＝被吃
        ((0.0, 0.0), (90.0, 90.0)),
        ((40.0, 0.0), (90.0, 90.0)),  # 重發之後：動了
    ])
    monkeypatch.setattr(board, "lattice_phase", lambda frame: next(reads))
    monkeypatch.setattr(board, "find_sightings", lambda frame: ())

    stroke = SweepRun.pan(run, "east", _blank(), 200.0)

    assert stroke == 200.0
    assert len(run.swipes) == 2
    assert run.swipes[0] == run.swipes[1]  # 原手勢原樣重發
    assert run.unlocks == [True]


def test_a_gesture_eaten_every_time_halts_instead_of_spinning(tmp_path, monkeypatch):
    run = swiping_run(tmp_path)
    monkeypatch.setattr(board, "lattice_phase", lambda frame: ((0.0, 0.0), (90.0, 90.0)))
    monkeypatch.setattr(board, "find_sightings", lambda frame: ())

    with pytest.raises(Halt):
        SweepRun.pan(run, "east", _blank(), 200.0)

    assert len(run.swipes) == sweep.GESTURE_EATEN_LIMIT


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
    run.pan = lambda direction, frame, reach=None: run.legs.append(direction)
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
