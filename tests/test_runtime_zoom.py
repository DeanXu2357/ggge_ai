"""地圖縮放：手勢幾何、中心挑選、後端注入接縫與收斂迴圈。全離線，不碰裝置。

凍結層那條 sendevent 路沒搬（SELinux 擋死），所以這裡測的是本機唯一跑得動的
GesturePincher 後端與它上面的 zoom_out_max。
"""

from __future__ import annotations

import numpy as np
import pytest

from ggge_ai.runtime import zoom
from ggge_ai.runtime.device import TapRefused
from ggge_ai.runtime.zoom import (
    FRAME_SOURCE,
    LATTICE_SOURCE,
    GesturePincher,
    PitchStep,
    ZoomOut,
    pick_pinch_center,
    zoom_out_fingers,
    zoom_out_max,
)


class Recorder:
    """Pincher 接縫的錄音機：真正的後端在實機上才存在。"""

    def __init__(self) -> None:
        self.calls: list[tuple[tuple, tuple]] = []

    def pinch(self, finger_a, finger_b) -> None:
        self.calls.append((finger_a, finger_b))




def test_zoom_out_fingers_is_a_pinch_in():
    a, b = zoom_out_fingers((1170, 500), start_span=1000, end_span=120)

    assert abs(b[0][0] - a[0][0]) == 1000  # 起手張開
    assert abs(b[1][0] - a[1][0]) == 120  # 收攏＝鏡頭拉遠
    assert a[0][1] == 500 and b[0][1] == 500  # 預設水平


def test_zoom_out_fingers_vertical_variant_swaps_the_axis():
    a, b = zoom_out_fingers((1170, 500), start_span=400, end_span=100, horizontal=False)

    assert a[0][0] == b[0][0] == 1170
    assert abs(b[0][1] - a[0][1]) == 400




def test_no_peaks_falls_back_to_the_fixed_center():
    assert pick_pinch_center([]) == zoom.PINCH_CENTER_DEFAULT


def _clearance(center, peaks):
    a, b = zoom_out_fingers(center)
    points = (a[0], a[1], b[0], b[1])
    return min(((px - ux) ** 2 + (py - uy) ** 2) ** 0.5 for px, py in points for ux, uy in peaks)


def test_a_cluster_under_the_fixed_center_moves_the_pinch():
    """起手點落在單位精靈上會被遊戲吃掉，所以中心要躲得比固定值遠。"""
    peaks = [(660, 500), (700, 480), (680, 520), (1170, 500), (1230, 500)]

    chosen = pick_pinch_center(peaks)

    assert chosen != zoom.PINCH_CENTER_DEFAULT
    assert _clearance(chosen, peaks) > _clearance(zoom.PINCH_CENTER_DEFAULT, peaks)


def test_every_chosen_center_keeps_its_four_points_in_the_safe_region():
    peaks = [(x, y) for x in range(500, 1900, 110) for y in range(340, 640, 90)]

    a, b = zoom_out_fingers(pick_pinch_center(peaks))

    rx, ry, rw, rh = zoom.PINCH_SAFE_REGION
    for px, py in (a[0], a[1], b[0], b[1]):
        assert rx <= px <= rx + rw and ry <= py <= ry + rh




def test_the_gesture_backend_maps_finger_pairs_onto_one_call():
    seen = []
    pincher = GesturePincher(gesture=lambda *args: seen.append(args), steps=40)

    pincher.pinch(((760, 540), (1120, 540)), ((1580, 540), (1220, 540)))

    # gesture(start1, start2, end1, end2, steps)：兩根手指的起點先、終點後
    assert seen == [((760, 540), (1580, 540), (1120, 540), (1220, 540), 40)]


def test_the_backend_is_wired_onto_the_game_surface_view():
    """手勢注在 Unity 繪圖面上才落在地圖，不是周邊 chrome。"""
    selectors: list[dict] = []
    seen: list[tuple] = []

    class FakeElement:
        def gesture(self, *args):
            seen.append(args)

    def device(**selector):
        selectors.append(selector)
        return FakeElement()

    zoom.gesture_pincher_for(device, steps=12).pinch(((0, 0), (1, 1)), ((2, 2), (3, 3)))

    assert selectors == [{"resourceId": zoom.SURFACE_RESOURCE_ID}]
    assert seen[0][-1] == 12




def _measured(sequence):
    frames = iter(range(len(sequence)))
    return frames, lambda frame: sequence[frame]


def test_two_pinches_without_shrinkage_end_the_zoom():
    sequence = [
        (128.0, 128.0, LATTICE_SOURCE),
        (118.0, 118.0, LATTICE_SOURCE),
        (108.0, 108.0, LATTICE_SOURCE),
        (100.0, 100.0, LATTICE_SOURCE),
        (99.0, 99.0, LATTICE_SOURCE),
        (99.0, 99.0, LATTICE_SOURCE),
        (99.0, 99.0, LATTICE_SOURCE),
    ]
    frames, measure = _measured(sequence)
    pinches = []

    steps = zoom_out_max(
        capture=lambda: next(frames),
        pinch_step=lambda: pinches.append(1),
        measure=measure,
        frame_change=lambda a, b: 5.0,
        sleep=lambda _: None,
        shrink_tol=1.5,
    )

    # 100 -> 99（縮不到 1.5px）與 99 -> 99 是兩次沒縮的高原
    assert steps[-1].index == 5
    assert len(pinches) == 5
    assert steps[-1].source == LATTICE_SOURCE


def test_an_unreadable_lattice_falls_back_to_the_frame_difference():
    """格線關著或被彈窗蓋住時仍要收斂：連兩幀幾乎不動就當停住。"""
    changes = iter([50.0, 10.0, 8.0, 1.0, 1.0, 1.0])
    frames = iter(range(10))

    steps = zoom_out_max(
        capture=lambda: next(frames),
        pinch_step=lambda: None,
        measure=lambda _: (None, None, None),
        frame_change=lambda a, b: next(changes),
        sleep=lambda _: None,
        change_tol=2.5,
    )

    assert steps[-1].source == FRAME_SOURCE
    assert steps[-1].change == 1.0


def test_every_step_is_reported_through_the_hook():
    sequence = [
        (120.0, None, LATTICE_SOURCE),
        (100.0, None, LATTICE_SOURCE),
        (100.0, None, LATTICE_SOURCE),
        (100.0, None, LATTICE_SOURCE),
    ]
    frames, measure = _measured(sequence)
    seen: list[PitchStep] = []

    zoom_out_max(
        capture=lambda: next(frames),
        pinch_step=lambda: None,
        measure=measure,
        frame_change=lambda a, b: 0.0,
        sleep=lambda _: None,
        on_step=seen.append,
    )

    assert [step.index for step in seen] == [0, 1, 2, 3]
    assert seen[0].col_pitch == 120.0


def test_the_pinch_budget_caps_a_camera_that_never_settles():
    """格距一直縮下去（量到鬼影）也要停：預算是防失控的上限。"""
    pitches = iter(float(200 - 10 * index) for index in range(50))
    frames = iter(range(50))

    steps = zoom_out_max(
        capture=lambda: next(frames),
        pinch_step=lambda: None,
        measure=lambda _: (next(pitches), None, LATTICE_SOURCE),
        frame_change=lambda a, b: 99.0,
        sleep=lambda _: None,
        max_pinches=3,
    )

    assert [step.index for step in steps] == [0, 1, 2, 3]




def blank() -> np.ndarray:
    return np.zeros((1080, 2340, 3), np.uint8)


def test_the_zoom_out_driver_pinches_until_the_frame_stops_changing():
    """空白幀＝讀不出格網也沒有位移：fail-soft 兩步就收斂，冪等。"""
    pincher = Recorder()
    captures = []

    driver = ZoomOut(
        capture=lambda: captures.append(1) or blank(), pincher=pincher, sleep=lambda _: None
    )
    driver()

    assert len(pincher.calls) == 2
    # 一次首幀 + 每次 pinch 後一幀；挑中心是吃迴圈抓過的那張，不另外多截。
    assert len(captures) == 3


def test_the_driver_repicks_the_centre_from_the_frame_it_just_captured(monkeypatch):
    """單位會吃掉起手點，所以每一步都拿當下那張幀重挑中心——而且是迴圈剛抓的
    那一張，不是另外補截的。"""
    looked: list[int] = []
    monkeypatch.setattr(zoom.board, "find_units", lambda frame: looked.append(frame[0, 0, 0]) or ())
    tint = iter(range(1, 9))

    def capture() -> np.ndarray:
        frame = blank()
        frame[:, :, 0] = next(tint)
        return frame

    ZoomOut(capture=capture, pincher=Recorder(), sleep=lambda _: None)()

    # 兩次 pinch 分別看到第 1 張與第 2 張幀（第 3 張是收斂後的最後量測）
    assert looked == [1, 2]


def test_a_finger_landing_outside_the_allowed_area_is_refused_not_injected(monkeypatch):
    """pinch 繞過裝置層的 tap 白名單，所以四個落點自己再過一次同一道檢查。"""
    monkeypatch.setattr(zoom, "pick_pinch_center", lambda peaks, **kwargs: (-500.0, 500.0))
    pincher = Recorder()
    driver = ZoomOut(capture=blank, pincher=pincher, sleep=lambda _: None)

    with pytest.raises(TapRefused):
        driver._pinch()

    assert pincher.calls == []
