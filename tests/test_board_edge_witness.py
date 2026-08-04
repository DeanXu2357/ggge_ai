"""投影校正的邊界目擊：`board.scan_edges` 逐幀逐側的三分裁決。

實幀取自 0803 第 8、9 輪的 survey 流水帳（`fixtures/vision/map_scan/edges_20260803/
manifest.json` 記著每一張的來源與期望）。這六張各鎖一個舊碼答錯的樣態：

- t21：鏡頭卡在西北角，格線只剩右下一角——舊碼的三閘錨在最外偵測格線上，那一角
  讀不到真邊（第 9 輪「角落錨不了」的直接死因）。
- t2、t58：西／北緣的正常目擊，守成用。
- t16：東緣落在取樣帶以外（線位框到 939、邊界在 1771），舊碼一律漏報。
- t15：同一條東緣往東再推一把之前的樣子。
- t1-precheck：斜的西邊界。未校正的原型在這裡判 blocked，校正之後判 EDGE——
  畫面站在 EDGE 這一邊（見下面兩條測試），這是本批唯一與原規格相左的裁決。
"""

from __future__ import annotations

import functools
from pathlib import Path

import cv2
import numpy as np
import pytest

from ggge_ai.runtime import board

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "vision" / "map_scan" / "edges_20260803"
# 位置容差。邊界位置是脊列延伸的終端線，逐幀抖動實測在個位數；20px 還不到四分之一格。
TOLERANCE = 20.0


@functools.cache
def frame(name: str) -> np.ndarray:
    image = cv2.imread(str(FIXTURES / f"{name}.png"))
    assert image is not None, name
    return image


@functools.cache
def edges(name: str) -> dict[str, tuple[str, float, dict]]:
    return board.scan_edges(frame(name))


def verdict(name: str, side: str) -> str:
    """那一側的裁決。整個軸讀不出脊列時該側缺席，一律當成「沒有目擊」。"""
    seen = edges(name).get(side)
    return "absent" if seen is None else seen[0]


def position(name: str, side: str) -> float:
    return edges(name)[side][1]


def _seen(name: str, side: str, at: float, tolerance: float = TOLERANCE) -> None:
    assert verdict(name, side) == board.EDGE_SEEN, edges(name).get(side)
    assert position(name, side) == pytest.approx(at, abs=tolerance)


def _unseen(name: str, *sides: str) -> None:
    for side in sides:
        assert verdict(name, side) != board.EDGE_SEEN, (side, edges(name).get(side))


def test_the_corner_frame_that_used_to_anchor_nothing_now_sees_two_edges():
    """第 9 輪的死因幀：鏡頭推到西北角，格線只剩畫面右下那一角。

    `read_lattice` 的全幀帶在這裡湊不到六欄四列，舊碼的終止邊三閘因此無邊可讀，
    `_anchor` 的「角落至少看得到一側」永遠不成立——推到底了卻錨不了世界。
    """
    _seen("t21-leg", "west", 1175.0)
    _seen("t21-leg", "north", 544.0)
    _unseen("t21-leg", "east", "south")


def test_a_plain_west_edge_is_read_where_the_gridlines_stop():
    _seen("t2-leg", "west", 1162.0)
    _unseen("t2-leg", "east", "north", "south")


def test_an_east_edge_beyond_the_sampling_band_is_no_longer_invisible():
    """東緣落在 `GRID_REGION`（到 x1750）以外。掃描窗取滿整幀寬才看得到它。"""
    _seen("t16-leg", "east", 1771.0, tolerance=60.0)
    assert 1740.0 <= position("t16-leg", "east") <= 1830.0
    _unseen("t16-leg", "west", "north", "south")


def test_a_north_edge_just_outside_the_window_is_picked_up_by_the_short_leash():
    """北緣 307 落在掃描窗（y330 起）之外：種子脊限在窗內，延伸放一個格距的短繩，
    這樣撿得回貼著窗外的終止線，又搆不到回合橫幅那條強邊緣。"""
    _seen("t58-leg", "north", 307.0)
    _seen("t58-leg", "west", 1175.0)
    _unseen("t58-leg", "east", "south")


def test_the_east_edge_one_pan_earlier_is_the_same_edge_further_east():
    """行為快照，不是人工地面真相：t15 的東緣 1943 與 t16 的 1771 相差 172px，
    與那一把東向推移量得的內容位移同級（單位排列比對 178px）——同一條實體邊。

    西側與南側同時鎖死：那兩側在這一幀被畫面切斷，不得出證言。
    """
    _seen("t15-leg", "east", 1943.0)
    _unseen("t15-leg", "west", "south")
    assert position("t15-leg", "east") - position("t16-leg", "east") == pytest.approx(
        172.0, abs=TOLERANCE
    )


def test_the_slanted_west_edge_is_a_real_edge_once_the_projection_is_taken_out():
    """**與本批原規格相左的一條**：規格要求這一幀的西側 ≠EDGE（沿用未校正原型的
    blocked）。校正之後判 EDGE@667。

    原型判 blocked 的原因不是「邊外還有殘餘格線」，而是終止線自己：那條線在螢幕上
    是斜的（0803 標定 slope=K·(x−XV)），640px 高的窗讓它橫跨 40px，底部那一帶因此
    滑進固定 x 的檢驗帶，帶檢驗讀到 max 50／peak 38 就一票否決。校正把線轉正，
    檢驗帶讀到的就只剩星空與美術（max 14／peak 74）。

    畫面站在 EDGE 這一邊，證據在下一條測試。
    """
    _seen("t1-precheck", "west", 667.0)
    _unseen("t1-precheck", "east", "north", "south")


def test_the_west_edge_of_that_frame_is_where_the_horizontal_lines_stop():
    """獨立於掃描器的佐證：橫向格線在 x≈667 以西就沒有了。

    取一條橫格線所在的列（y930）與它上下的參照列相減——線在的地方對比為正。邊界
    以東平均 116，以西平均 1.3，也就是說那一側的格網真的到此為止。
    """
    grey = cv2.cvtColor(frame("t1-precheck"), cv2.COLOR_BGR2GRAY).astype(np.float32)
    line = grey[929:933].mean(axis=0)
    around = (grey[916:922].mean(axis=0) + grey[939:945].mean(axis=0)) / 2.0
    contrast = line - around

    assert contrast[480:640].mean() < 5.0
    assert contrast[700:900].mean() > 50.0


def test_a_border_may_sit_outside_the_box_the_lattice_band_could_read():
    """線位框與邊界位置從此是兩件事：框來自 `GRID_REGION` 帶，邊界來自全幀掃描。"""
    span = board.read_span(frame("t16-leg"))

    assert span is not None
    box = span.box
    assert span.border("east") is not None
    assert span.border("east") > box[0] + box[2]
    assert span.edges == frozenset({"east"})
    assert dict(span.borders) == {"east": span.border("east")}



LINE_SPACING = 93
LINE_VALUE = 210


def _projected_grid() -> np.ndarray:
    """按標定的斜率場畫一張假格網：縱線在 y=PERSPECTIVE_REF_Y 上通過 u，往上下按
    x = XV + (u − XV)·(1 + K·(y − Y_REF)) 傾斜。"""
    canvas = np.full((1080, 2340, 3), 20, np.uint8)
    rows = np.arange(1080, dtype=np.float32)
    scale = 1.0 + board.PERSPECTIVE_K * (rows - board.PERSPECTIVE_REF_Y)
    for u in range(60, 2340, LINE_SPACING):
        xs = board.PERSPECTIVE_VP_X + (u - board.PERSPECTIVE_VP_X) * scale
        for offset in (0, 1):
            valid = (xs + offset >= 0) & (xs + offset < 2340)
            canvas[rows[valid].astype(int), (xs[valid] + offset).astype(int)] = LINE_VALUE
    return canvas


def _spread(image: np.ndarray, column: int, half: int = 30) -> int:
    """同一條線在各列的峰位差：完全轉正的線是 0。"""
    x0, y0, _, h = board.EDGE_SCAN_REGION
    peaks = [
        int(np.argmax(image[row, column - x0 - half : column - x0 + half]))
        for row in range(0, h, 40)
    ]
    return max(peaks) - min(peaks)


def test_rectifying_columns_makes_the_slanted_lines_stand_up_straight():
    patch = board.crop(_projected_grid(), board.EDGE_SCAN_REGION)
    rectified, valid = board.rectify_columns(patch)

    for column in range(int(valid[0]) + 100, int(valid[1]) - 100, LINE_SPACING * 3):
        line = min(
            range(60, 2340, LINE_SPACING), key=lambda candidate: abs(candidate - column)
        )
        assert _spread(rectified[:, :, 0], line) <= 2, line
        assert _spread(patch[:, :, 0], line) >= 2


def test_the_rectified_frame_says_which_columns_it_can_still_answer_for():
    """有效範圍以外每一列的來源不同，投影是被稀釋過的——不可取樣，這是坑。"""
    patch = board.crop(_projected_grid(), board.EDGE_SCAN_REGION)
    _, valid = board.rectify_columns(patch)
    x0, _, w, _ = board.EDGE_SCAN_REGION

    assert x0 < valid[0] < x0 + 60
    assert x0 + w - 60 < valid[1] < x0 + w
    assert valid[0] == pytest.approx(39.7, abs=1.0)
    assert valid[1] == pytest.approx(2299.1, abs=1.0)


def test_a_frame_with_no_perspective_is_read_where_its_lines_actually_are():
    """校正模型對不對由畫面自己裁：沒有透視的輸入（線本來就是正的）校正只會把線
    攤平，脊的中位峰高因此掉一大截，掃描就改讀原樣的空間。"""
    straight = np.full((1080, 2340, 3), 20, np.uint8)
    for x in range(300, 2100, LINE_SPACING):
        straight[300:1000, x : x + 2] = LINE_VALUE

    highpass = board._highpass(board.crop(straight, board.EDGE_SCAN_REGION))
    image, limits = board._column_space(highpass, board.EDGE_SCAN_REGION)
    run = board._ridge_run(image.mean(axis=0), board.EDGE_SCAN_REGION[0], limits)

    assert run is not None
    assert run[0][0] == pytest.approx(300.0, abs=2.0)
    assert run[1] == pytest.approx(LINE_SPACING, abs=1.0)
