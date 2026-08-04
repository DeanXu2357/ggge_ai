"""每格點擊清算掃描：不看弧色，逐格點一次，用點擊回饋裁決那一格。

與 `runtime/coverage.py` 的弧色掃描完全並行，兩邊互不呼叫。三分裁決：

- 點空格 → 那一格填出半透明填色（全圖唯一，點別格會搬走）＝ EMPTY
- 點到單位 → 出摘要卡，橫幅停靠側判陣營 ＝ ENEMY／ALLY
- 點到我方 → 進選擇狀態、鏡頭自動置中 ＝ SHIFTED（重錨後仍記 ALLY）

不變量：帳本**只收點擊裁決過的事實，一律記世界格**。分不出結果的格記 UNSURE
留白——寧可留白不留假帳。

出卡讀取、陣營裁決與 escape 鏈住 `battle/`，這一層不得 import 它（新包自足），
所以那幾件事一律由呼叫端以 callable 注入。
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from . import board
from .board import Cell, MarkerSignature, Point, Region
from .coverage import WorldGrid
from .device import DANGER_BANDS, DangerBand

log = logging.getLogger(__name__)

UNKNOWN = "unknown"
EMPTY = "empty"
ENEMY = "enemy"
ALLY = "ally"
UNSURE = "unsure"
DECIDED: tuple[str, ...] = (EMPTY, ENEMY, ALLY, UNSURE)

COMPASS: tuple[str, ...] = ("west", "east", "north", "south")
_SIDES: dict[str, tuple[str, str]] = {"x": ("west", "east"), "y": ("north", "south")}

# 安全點擊窗＝地圖區：上緣避開回合橫幅帶、下緣停在鈕列之上。窗外的格不點，
# 等推鏡把它輪進來。
TAP_REGION: Region = board.MAP_REGION
SCREEN_CENTRE: Point = (board.MAP_REGION[0] + board.MAP_REGION[2] / 2.0, 540.0)

TAP_EMPTY = "empty"
TAP_CARD = "card"
TAP_SHIFTED = "shifted"
TAP_NONE = "none"

SOURCE_EDGE = "edge"
SOURCE_CENTRE = "centre"
SOURCE_MIXED = "mixed"
SOURCE_LOST = "lost"

# 填色要落在**被點的那一格**：半格容差內才算數，落到隔壁就是認錯了地標。
MARKER_HIT_PITCH = 0.5
# 內容位移超過這麼多像素＝鏡頭被置中拉走。一格約 90，六成格已遠大於偵測抖動。
CENTRE_SHIFT_PX = 60.0
# 同軸兩側地標各算一次偏移，差超過半格就是至少一側不是地圖邊，整軸不採信。
EDGE_AGREEMENT_PITCH = 0.5

HEADINGS: tuple[str, str] = ("east", "west")


def screen_of(grid: WorldGrid, cell: Cell, offset: Point) -> Point:
    centre = grid.centre_of(cell)
    return (centre[0] - offset[0], centre[1] - offset[1])


def border_cell(grid: WorldGrid, direction: str, border: float) -> int:
    """終止邊往界內半格＝該側最外一格的格座標。"""
    pitch = grid.col_pitch if direction in ("west", "east") else grid.row_pitch
    inward = pitch / 2.0 if direction in ("west", "north") else -pitch / 2.0
    if direction in ("west", "east"):
        return grid.cell_of((border + inward, grid.phase[1]))[0]
    return grid.cell_of((grid.phase[0], border + inward))[1]


@dataclass
class SweepLedger:
    """世界格帳本。每一筆都由一次點擊裁決背書，永遠不記螢幕座標。"""

    grid: WorldGrid
    state: dict[Cell, str] = field(default_factory=dict)
    names: dict[Cell, str] = field(default_factory=dict)
    frames: dict[Cell, str] = field(default_factory=dict)
    reasons: dict[Cell, str] = field(default_factory=dict)
    boundary: dict[str, int] = field(default_factory=dict)
    charted: set[Cell] = field(default_factory=set)
    blocked: dict[Cell, int] = field(default_factory=dict)
    taps: int = 0

    def verdict(self, cell: Cell) -> str:
        return self.state.get(cell, UNKNOWN)

    def decided(self, cell: Cell) -> bool:
        return self.verdict(cell) in DECIDED

    def chart(self, cell: Cell) -> None:
        self.charted.add(cell)

    def record(
        self,
        cell: Cell,
        verdict: str,
        *,
        name: str | None = None,
        frame: str | None = None,
        reason: str | None = None,
    ) -> None:
        if verdict not in DECIDED:
            raise ValueError(f"not a decided verdict: {verdict!r}")
        self.chart(cell)
        self.state[cell] = verdict
        self.blocked.pop(cell, None)
        if name:
            self.names[cell] = name
        if frame:
            self.frames[cell] = frame
        if reason:
            self.reasons[cell] = reason

    def defer(self, cell: Cell) -> None:
        """這個鏡位下進不了安全窗；等推鏡把它輪過來。"""
        self.chart(cell)
        if not self.decided(cell):
            self.blocked[cell] = self.blocked.get(cell, 0) + 1

    def see_border(self, direction: str, world: float) -> None:
        """界線一律目視。第一次記下就不再改——寫錯的代價是永久的。"""
        if direction in self.boundary:
            return
        self.boundary[direction] = border_cell(self.grid, direction, world)

    @property
    def bounded(self) -> bool:
        return all(direction in self.boundary for direction in COMPASS)

    def in_bounds(self, cell: Cell) -> bool:
        col, row = cell
        limits = (
            ("west", col, 1),
            ("east", col, -1),
            ("north", row, 1),
            ("south", row, -1),
        )
        for direction, value, sign in limits:
            edge = self.boundary.get(direction)
            if edge is not None and sign * (value - edge) < 0:
                return False
        return True

    def rectangle(self) -> tuple[Cell, ...]:
        if not self.bounded:
            return ()
        return tuple(
            (col, row)
            for row in range(self.boundary["north"], self.boundary["south"] + 1)
            for col in range(self.boundary["west"], self.boundary["east"] + 1)
        )

    def pending(self) -> tuple[Cell, ...]:
        cells = self.rectangle() if self.bounded else tuple(sorted(self.charted))
        return tuple(cell for cell in cells if self.in_bounds(cell) and not self.decided(cell))

    @property
    def complete(self) -> bool:
        """建構性判準：四界都定 ∧ 界內每格都裁決過（UNSURE 也算裁決過）。"""
        return self.bounded and not self.pending()

    def cells_of(self, verdict: str) -> tuple[Cell, ...]:
        return tuple(sorted(cell for cell, value in self.state.items() if value == verdict))

    def summary(self) -> dict[str, Any]:
        counts = {value: len(self.cells_of(value)) for value in DECIDED}
        return {
            "bounded": self.bounded,
            "complete": self.complete,
            "boundary": dict(sorted(self.boundary.items())),
            "counts": counts,
            "taps": self.taps,
            "enemies": [
                {"cell": list(cell), "name": self.names.get(cell)} for cell in self.cells_of(ENEMY)
            ],
            "allies": [list(cell) for cell in self.cells_of(ALLY)],
            "unsure": [
                {"cell": list(cell), "reason": self.reasons.get(cell)}
                for cell in self.cells_of(UNSURE)
            ],
            "pending": len(self.pending()),
            "deferred": [list(cell) for cell in sorted(self.blocked)],
        }


@dataclass(frozen=True)
class TapTarget:
    cell: Cell
    point: Point


@dataclass(frozen=True)
class WindowPlan:
    """本鏡位下要點的格（蛇形）與擋掉的格。blocked 是這個鏡位的事實，不是永久的。"""

    taps: tuple[TapTarget, ...]
    blocked: tuple[Cell, ...]
    window: tuple[Cell, Cell] | None = None


def _tap_blocked(point: Point, bands: Sequence[DangerBand]) -> bool:
    x, y = int(round(point[0])), int(round(point[1]))
    # 格點擊不帶 intent，所以帶內一律不放行（白名單制）。
    return any(band.contains(x, y) for band in bands)


def _box_overlaps(box: tuple[float, float, float, float], region: Region) -> bool:
    x, y, w, h = region
    return not (box[2] <= x or box[0] >= x + w or box[3] <= y or box[1] >= y + h)


def _box_within(box: tuple[float, float, float, float], region: Region) -> bool:
    x, y, w, h = region
    return box[0] >= x and box[1] >= y and box[2] <= x + w and box[3] <= y + h


def window_bounds(
    grid: WorldGrid, offset: Point, region: Region = TAP_REGION
) -> tuple[Cell, Cell]:
    x, y, w, h = region
    first = grid.cell_of((x + offset[0], y + offset[1]))
    last = grid.cell_of((x + w + offset[0], y + h + offset[1]))
    return (first, last)


def plan_window(
    ledger: SweepLedger,
    offset: Point,
    *,
    heading: str = "east",
    region: Region = TAP_REGION,
    holes: Sequence[Region] = board.UNIT_DENSITY_HUD_HOLES,
    bands: Sequence[DangerBand] = DANGER_BANDS,
) -> WindowPlan:
    """本鏡位裡還沒裁決、點得下去的格，蛇形排序。

    整格框要**完整**落在點擊窗內：被窗邊切一半的格點下去可能命中隔壁那一格，而
    帳本收的是「這一格的事實」。
    """
    grid = ledger.grid
    first, last = window_bounds(grid, offset, region)
    taps: list[TapTarget] = []
    blocked: list[Cell] = []
    rows = range(first[1], last[1] + 1)
    for index, row in enumerate(rows):
        cols = list(range(first[0], last[0] + 1))
        if (heading == "west") != (index % 2 == 1):
            cols.reverse()
        for col in cols:
            cell = (col, row)
            bx0, by0, bx1, by1 = grid.box_of(cell)
            box = (bx0 - offset[0], by0 - offset[1], bx1 - offset[0], by1 - offset[1])
            if not _box_within(box, region):
                continue
            if not ledger.in_bounds(cell):
                continue
            ledger.chart(cell)
            if ledger.decided(cell):
                continue
            point = ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)
            if any(_box_overlaps(box, hole) for hole in holes) or _tap_blocked(point, bands):
                blocked.append(cell)
                continue
            taps.append(TapTarget(cell, point))
    return WindowPlan(tuple(taps), tuple(blocked), (first, last))


def plan_pan(
    ledger: SweepLedger,
    offset: Point,
    heading: str = "east",
    *,
    region: Region = TAP_REGION,
) -> tuple[str | None, str]:
    """下一段推鏡方向與更新後的橫向朝向。沒得推就 (None, heading)。

    沿列帶蛇形推進；**界線未見的方向優先探**——那個方向的格還沒被枚舉過，
    「界內沒有待裁決的格」在那裡不成立。
    """
    if heading not in HEADINGS:
        heading = "east"
    if _more_that_way(ledger, offset, heading, region):
        return (heading, heading)
    flipped = "west" if heading == "east" else "east"
    if _more_that_way(ledger, offset, "south", region):
        return ("south", flipped)
    if _more_that_way(ledger, offset, "north", region):
        return ("north", flipped)
    return (None, heading)


def _more_that_way(
    ledger: SweepLedger, offset: Point, direction: str, region: Region
) -> bool:
    if direction not in ledger.boundary:
        return True
    first, last = window_bounds(ledger.grid, offset, region)
    limits = {
        "east": lambda cell: cell[0] > last[0],
        "west": lambda cell: cell[0] < first[0],
        "south": lambda cell: cell[1] > last[1],
        "north": lambda cell: cell[1] < first[1],
    }
    beyond = limits[direction]
    return any(beyond(cell) for cell in ledger.pending())


@dataclass(frozen=True)
class TapOutcome:
    """一次點擊的回饋三分類。delta ＝ 量得到的內容位移（置中時才有意義）。"""

    verdict: str
    delta: Point | None = None
    marker: Point | None = None
    learned: MarkerSignature | None = None


def _displacement(before: np.ndarray, after: np.ndarray) -> Point | None:
    delta = board.relocalise(board.find_units(before), board.find_units(after))
    return None if delta is None else (float(delta[0]), float(delta[1]))


def classify_tap(
    before: np.ndarray,
    after: np.ndarray,
    target: Point,
    *,
    signature: MarkerSignature | None = None,
    card: Callable[[np.ndarray], bool] | None = None,
    displace: Callable[[np.ndarray, np.ndarray], Point | None] | None = None,
    pitch: tuple[float, float] | None = None,
    region: Region = board.MAP_REGION,
) -> TapOutcome:
    """點擊前後幀 → EMPTY／CARD／SHIFTED／NONE。

    順序有意義：出卡先問（卡片本身就是答案），置中次之（鏡頭一動，「填色在不在被
    點的那一格」這個問法就失去意義），最後才問填色。

    還沒有色簽時用 `learn_marker` 現學：**第一次點到空格**同時是學色簽的唯一機會，
    學到了就回傳給呼叫端收下。
    """
    if card is not None and card(after):
        return TapOutcome(TAP_CARD)
    moved = (displace or _displacement)(before, after)
    if moved is not None and math.hypot(*moved) >= CENTRE_SHIFT_PX:
        return TapOutcome(TAP_SHIFTED, delta=moved)
    if signature is not None:
        found = board.find_marker(after, signature, region=region)
        if found is not None and _near(found, target, pitch or signature.size):
            return TapOutcome(TAP_EMPTY, marker=found)
        return TapOutcome(TAP_NONE)
    learned = board.learn_marker(before, after, target, region=region)
    if learned is not None:
        return TapOutcome(TAP_EMPTY, marker=target, learned=learned)
    return TapOutcome(TAP_NONE)


def _near(point: Point, target: Point, pitch: tuple[float, float]) -> bool:
    return (
        abs(point[0] - target[0]) <= MARKER_HIT_PITCH * pitch[0]
        and abs(point[1] - target[1]) <= MARKER_HIT_PITCH * pitch[1]
    )


def recentre_offset(grid: WorldGrid, cell: Cell, centre: Point = SCREEN_CENTRE) -> Point:
    """置中發生時：被點的那一格就是螢幕中心格，鏡位由它反推。"""
    world = grid.centre_of(cell)
    return (world[0] - centre[0], world[1] - centre[1])


def border_offsets(
    grid: WorldGrid,
    landmarks: Mapping[str, float],
    borders: Mapping[str, float],
) -> dict[str, float]:
    """由已記的地圖終止邊（世界像素）與這一幀的螢幕終止邊解出的逐軸鏡位。

    同軸兩側都讀得到就要互相對得上——差太多代表至少一側不是地圖邊，整軸不採信。
    """
    out: dict[str, float] = {}
    for axis, sides in _SIDES.items():
        slack = EDGE_AGREEMENT_PITCH * (grid.col_pitch if axis == "x" else grid.row_pitch)
        readings = [
            landmarks[side] - borders[side]
            for side in sides
            if side in landmarks and side in borders
        ]
        if not readings:
            continue
        if max(readings) - min(readings) > slack:
            continue
        out[axis] = sum(readings) / len(readings)
    return out


def reanchor(
    grid: WorldGrid,
    *,
    landmarks: Mapping[str, float],
    borders: Mapping[str, float],
    candidate: Point | None = None,
) -> tuple[Point | None, str]:
    """重錨：地標（絕對）優先，置中反推的候選只補地標沒說話的那一軸。

    地標與候選矛盾時**地標說了算**，因為地標不會被置中演出弄錯；兩者都沒有就回
    (None, lost)，呼叫端只剩回角落歸零這一條路。
    """
    axes = border_offsets(grid, landmarks, borders)
    if "x" in axes and "y" in axes:
        return ((axes["x"], axes["y"]), SOURCE_EDGE)
    if candidate is None:
        return (None, SOURCE_LOST)
    if not axes:
        return (candidate, SOURCE_CENTRE)
    return (
        (axes.get("x", candidate[0]), axes.get("y", candidate[1])),
        SOURCE_MIXED,
    )


def anchor_northwest(
    lattice: board.Lattice, borders: Mapping[str, float]
) -> tuple[WorldGrid, Point] | None:
    """西北角幀 → 世界座標系：西界＝世界 x 0、北界＝世界 y 0。

    座標在這裡是被**定義**的，不是量出來的；角落可重現，所以跨輪重新歸零回到同一套。
    """
    if "west" not in borders or "north" not in borders:
        return None
    offset = (-float(borders["west"]), -float(borders["north"]))
    grid = WorldGrid.anchor(lattice, offset)
    if grid is None:
        return None
    return (grid, offset)


def read_borders(frame: np.ndarray) -> dict[str, float]:
    """這一幀目視到的終止邊（螢幕像素），只收裁決為 EDGE 的那幾側。"""
    return {
        side: float(position)
        for side, (verdict, position, _) in board.scan_edges(frame).items()
        if verdict == board.EDGE_SEEN
    }


def serpentine(cells: Iterable[Cell], heading: str = "east") -> tuple[Cell, ...]:
    """列帶蛇形排序（離線規劃與測試共用）。"""
    rows: dict[int, list[int]] = {}
    for col, row in cells:
        rows.setdefault(row, []).append(col)
    out: list[Cell] = []
    for index, row in enumerate(sorted(rows)):
        cols = sorted(rows[row], reverse=(heading == "west") != (index % 2 == 1))
        out.extend((col, row) for col in cols)
    return tuple(out)
