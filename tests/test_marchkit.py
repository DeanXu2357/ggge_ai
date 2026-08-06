"""marchkit：推鏡逐手勢驗收與種標記驗收。

case 逐條對應 `tests/test_sweep_scan.py` 的同名測試（搬運不重寫，行為差異零容忍）：
`an_eaten_gesture_is_unlocked_and_resent_unchanged`、
`a_gesture_eaten_every_time_halts_instead_of_spinning`（模組層改回 verdict，不 raise）、
`pushing_past_a_visible_border_is_exhaustion_not_an_eaten_gesture`、
`a_full_stroke_the_phase_could_not_see_is_still_a_landed_gesture`、
`a_pinned_camera_turns_instead_of_halting_and_writes_no_border`、
`a_vertical_push_is_shortened_so_the_row_pitch_cannot_hide_it`、
`a_carry_tap_with_no_fill_is_retried_and_never_moves_the_marker_cell`。
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from ggge_ai.runtime import board, marchkit, sweep
from ggge_ai.runtime.journal import Journal


def _blank() -> np.ndarray:
    return np.zeros((1080, 2340, 3), np.uint8)


def _marcher(tmp_path) -> marchkit.Marcher:
    swipes: list[tuple] = []
    unlocks: list[bool] = []
    taps: list[tuple[int, int]] = []
    device = SimpleNamespace(
        tap=lambda x, y, intent="": taps.append((x, y)),
        swipe=lambda *args: swipes.append(args),
        ensure_unlocked=lambda force=False: unlocks.append(force),
    )
    marcher = marchkit.Marcher(
        device=device,
        camera=SimpleNamespace(grab=_blank),
        journal=Journal(tmp_path / "march.jsonl"),
        sleep=lambda _: None,
    )
    marcher.swipes, marcher.unlocks, marcher.taps = swipes, unlocks, taps  # type: ignore[attr-defined]
    return marcher


def _phase_only(monkeypatch, reads):
    """標記看不見的鏡位：驗收只剩相位。"""
    monkeypatch.setattr(board, "lattice_phase", lambda frame: next(reads))
    monkeypatch.setattr(board, "find_sightings", lambda frame: ())


def test_an_eaten_gesture_is_unlocked_and_resent_unchanged(tmp_path, monkeypatch):
    marcher = _marcher(tmp_path)
    _phase_only(
        monkeypatch,
        iter(
            [
                ((0.0, 0.0), (80.0, 80.0)),  # 推之前
                ((0.0, 0.0), (80.0, 80.0)),  # 推之後：相位沒動＝被吃
                ((40.0, 0.0), (80.0, 80.0)),  # 重發之後：動了
            ]
        ),
    )

    result = marcher.pan("east", _blank(), 200.0)

    assert (result.stroke, result.verdict) == (200.0, sweep.PAN_LANDED)
    assert len(marcher.swipes) == 2
    assert marcher.swipes[0] == marcher.swipes[1]  # 原手勢原樣重發
    assert marcher.unlocks == [True]  # 重發之前先做解鎖檢查


def test_a_gesture_eaten_every_time_stops_instead_of_spinning(tmp_path, monkeypatch):
    """sweep_scan 在這裡 raise Halt；模組層改回 `PAN_EATEN` 讓呼叫端裁決，次數不變。"""
    marcher = _marcher(tmp_path)
    monkeypatch.setattr(board, "lattice_phase", lambda frame: ((0.0, 0.0), (80.0, 80.0)))
    monkeypatch.setattr(board, "find_sightings", lambda frame: ())

    result = marcher.pan("east", _blank(), 200.0)

    assert result.verdict == sweep.PAN_EATEN
    assert len(marcher.swipes) == sweep.GESTURE_EATEN_LIMIT


def test_pushing_past_a_visible_border_is_exhaustion_not_an_eaten_gesture(tmp_path, monkeypatch):
    marcher = _marcher(tmp_path)
    monkeypatch.setattr(board, "lattice_phase", lambda frame: ((0.0, 0.0), (90.0, 90.0)))
    monkeypatch.setattr(board, "find_sightings", lambda frame: ())
    monkeypatch.setattr(sweep, "read_borders", lambda frame: {"north": 120.0})

    result = marcher.pan("north", _blank(), 200.0)

    assert (result.stroke, result.verdict) == (0.0, marchkit.PAN_BORDER)
    assert len(marcher.swipes) == 1  # 不重發、不停手
    assert marcher.unlocks == []


def _pinning(tmp_path, monkeypatch, marks):
    marcher = _marcher(tmp_path)
    marcher.signature = object()
    monkeypatch.setattr(board, "lattice_phase", lambda frame: None)
    monkeypatch.setattr(board, "find_sightings", lambda frame: ())
    monkeypatch.setattr(sweep, "read_borders", lambda frame: {})
    points = iter(marks)
    monkeypatch.setattr(board, "find_marker", lambda frame, sig, **kw: next(points))
    return marcher


def test_a_full_stroke_the_phase_could_not_see_is_still_a_landed_gesture(tmp_path, monkeypatch):
    marcher = _pinning(tmp_path, monkeypatch, [(1400.0, 800.0), (1400.0, 550.0)])

    result = marcher.pan("south", _blank(), 260.0)

    assert (result.stroke, result.verdict) == (260.0, sweep.PAN_LANDED)
    assert len(marcher.swipes) == 1
    assert marcher.pinned == set()


def test_a_pinned_camera_turns_instead_of_halting_and_writes_no_border(tmp_path, monkeypatch):
    marks = [(1400.0, 800.0), (1400.0, 806.0)] * sweep.GESTURE_PINNED_LIMIT
    marcher = _pinning(tmp_path, monkeypatch, marks)

    result = marcher.pan("south", _blank(), 260.0)

    assert (result.stroke, result.verdict) == (0.0, sweep.PAN_PINNED)
    assert marcher.pinned == {"south"}
    assert marcher.unlocks == []  # 夾停不是被吃，不做解鎖重發
    assert len(marcher.swipes) == sweep.GESTURE_PINNED_LIMIT


def test_a_vertical_push_is_shortened_so_the_row_pitch_cannot_hide_it(tmp_path, monkeypatch):
    """0805-031635 的 Halt：row_pitch 85 上推滿 260，相位殘量落回 0 附近＝真的走了卻
    讀成被吃。行程先讓路給相位，這條鏈才判得出來。"""
    marcher = _marcher(tmp_path)
    _phase_only(monkeypatch, iter([((0.0, 0.0), (90.5, 85.0)), ((0.0, -27.0), (90.5, 85.0))]))

    result = marcher.pan("north", _blank(), 260.0)

    assert result.stroke < 260.0
    assert abs(board._wrap_phase(board.PAN_GAIN * result.stroke, 85.0)) >= (
        board.PHASE_LEGIBLE_MARGIN
    )
    x1, y1, _, y2 = marcher.swipes[0][:4]
    assert y2 - y1 == round(result.stroke)  # 手勢真的照縮過的行程打出去


def test_a_seed_tap_with_no_fill_is_retried_and_never_becomes_a_marker(tmp_path, monkeypatch):
    """點下去說不出結果就重拍重點一次；沒驗到填色就**不准**更新標記。"""
    marcher = _marcher(tmp_path)
    monkeypatch.setattr(sweep, "classify_tap", lambda *a, **k: sweep.TapOutcome(sweep.TAP_NONE))

    placed = marcher.place_marker(
        (900.0, 500.0), _blank(), pitch=(128.0, 120.0), card=lambda frame: False
    )

    assert not placed.ok and placed.signature is None
    assert marcher.taps == [(900, 500), (900, 500)]
    assert marcher.signature is None


def test_a_verified_fill_is_the_only_thing_that_becomes_a_marker(tmp_path, monkeypatch):
    marcher = _marcher(tmp_path)
    learned = board.MarkerSignature(hsv=(100, 200, 200), tolerance=(5, 40, 40), size=(40.0, 40.0))
    monkeypatch.setattr(
        sweep,
        "classify_tap",
        lambda *a, **k: sweep.TapOutcome(sweep.TAP_EMPTY, learned=learned, marker=(901.0, 501.0)),
    )

    placed = marcher.place_marker(
        (900.0, 500.0), _blank(), pitch=(128.0, 120.0), card=lambda frame: False
    )

    assert placed.ok and placed.signature is learned
    assert marcher.signature is learned
    assert marcher.taps == [(900, 500)]


def test_a_marker_that_cannot_be_seen_is_gone(tmp_path, monkeypatch):
    """記著的標記在這一幀看不見＝它已經沒了，再拿它當證人就是舊填色配新格號。"""
    marcher = _marcher(tmp_path)
    marcher.signature = object()
    monkeypatch.setattr(board, "find_marker", lambda frame, sig, **kw: None)

    assert marcher.marker_gone(_blank())


def test_the_stride_never_pushes_the_marker_out_of_the_next_window(tmp_path):
    marcher = _marcher(tmp_path)

    near_edge = marcher.stride((2200.0, 500.0), "west", 128.0, board.PAN_MAX_REACH)
    room = marcher.stride((400.0, 500.0), "west", 128.0, board.PAN_MAX_REACH)

    assert near_edge < room
    assert near_edge >= board.PAN_MIN_REACH


@pytest.mark.parametrize("direction", ["west", "north"])
def test_a_marchless_caller_still_gets_a_capped_stroke(tmp_path, direction):
    """標記看不見時沒有上限可算，行程照樣被夾在 PAN_MIN/MAX 之間。"""
    marcher = _marcher(tmp_path)

    assert marcher.stride(None, direction, 128.0, 10_000.0) == board.PAN_MAX_REACH
