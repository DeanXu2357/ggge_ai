"""停滯判定的佐證門檻：近乎零的位移讀數什麼時候才算「畫面沒動」的證言。

實幀來自 0803 第 8 輪（`tests/fixtures/vision/map_scan/stall_20260803/manifest.json`
記著來源與裁切）。那一輪繞邊的東向段 t15、t16 每把都真的推動了約 178px，相位相關
卻凍住讀成 0.8px；連兩把被算成推不動，東側於是在鏡頭還沒到地圖東緣時就被從路線裡
拿掉，整輪東、南兩側一次都沒讀到終止邊。

裁切的幀貼回同座標的全尺寸黑底畫布再送進判定：`_unchanged` 取樣的是 `MAP_REGION`，
而裁切框就是它，所以量測輸入與原幀逐像素相同。
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from ggge_ai.runtime import board, coverage
from ggge_ai.runtime.coverage import Leg, Survey

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "vision" / "map_scan" / "stall_20260803"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
CROP = tuple(MANIFEST["crop"])
CANVAS = (1080, 2340, 3)

# 第 16 把東向推移的指令位移（流水帳 data/runs/20260803-075745/dry_run.jsonl 的 expected）。
EAST_LEG = Leg("east", 260.0, (-400.0, 0.0))


def _frame(name: str) -> np.ndarray:
    crop = cv2.imread(str(FIXTURES / name))
    assert crop is not None, name
    x, y, w, h = CROP
    assert crop.shape[:2] == (h, w), crop.shape
    canvas = np.zeros(CANVAS, np.uint8)
    canvas[y : y + h, x : x + w] = crop
    return canvas


@pytest.fixture(scope="module")
def frames() -> dict[str, np.ndarray]:
    return {name: _frame(f"{name}.png") for name in ("t15-leg", "t16-precheck", "t16-leg")}


def test_a_frozen_correlator_is_no_witness_that_the_screen_stayed_put(frames):
    """凍住的量測器不准被判成沒動。

    回應 0.063 ＝ 雜訊等級，讀數近乎零因此什麼都證明不了：相關器凍住時輸出的正是
    近乎零，與「真的沒動」的正解重合。舊碼只問 `known`，而 `known` 在這個回應下照樣
    為真，所以「量不出來一律當作動過」那條教義永遠走不到。
    """
    previous, current = frames["t16-precheck"], frames["t16-leg"]

    _, _, response = board._phase_shift(previous, current, board.MAP_REGION)
    frozen = board.measure_shift(previous, current)
    assert frozen.known and frozen.magnitude < board.EDGE_SHIFT_PX
    assert board.SHIFT_MIN_RESPONSE < response < board.STILL_MIN_RESPONSE

    assert not Survey()._unchanged(previous, current, EAST_LEG)


def test_the_screen_really_did_move_and_the_arrangement_of_units_says_so(frames):
    """把那一把的位移交給不同源的證言：單位排列比對量得到一整把推移的量。

    這是「東側不該被拿掉」的地面真相——不是推論，是畫面裡的機體真的整批西移了。
    """
    shift = board.measure_shift(
        frames["t16-precheck"], frames["t16-leg"], min_response=board.STILL_MIN_RESPONSE
    )

    assert shift.known
    assert shift.magnitude > 150.0


def test_a_screen_that_really_did_not_move_is_still_called_still(frames):
    """真的沒動仍要判成沒動——歸零正是靠連兩次推不動才錨定的，這一條鬆掉就永遠結束不了。

    t15-leg 與 t16-precheck 之間沒有任何手勢，兩幀逐像素幾乎相同。
    """
    previous, current = frames["t15-leg"], frames["t16-precheck"]

    assert board.frame_difference(previous, current) < board.EDGE_FRAME_DIFF

    assert Survey()._unchanged(previous, current, None)
    assert Survey()._unchanged(previous, current, EAST_LEG)


def test_two_frozen_readings_never_retire_the_side_from_the_tour(frames):
    """畫面還在動的時候，那一側不准被從沿邊繞圈的路線裡拿掉。

    第 8 輪的實際後果就在這一條：t15、t16 兩把被誤判成推不動之後，`_tour_leg` 在 t17
    直接換到南側，鏡頭根本還沒推到地圖東緣。
    """
    survey = Survey()
    survey.stance = coverage.TOUR
    survey.previous = frames["t16-precheck"]

    for _ in range(coverage.STALL_CONFIRM):
        survey._tally(EAST_LEG.direction, survey._unchanged(survey.previous, frames["t16-leg"], EAST_LEG))

    assert survey.stalls.get("east", 0) == 0
    assert survey.route[0] == "east"
    leg = survey._tour_leg()
    assert leg is not None and leg.direction == "east"
