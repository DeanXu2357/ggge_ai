"""名冊跳轉掃描的純邏輯：落點鎖定、記帳、共現複核、排程、解除點挑選。

跳轉是硬切（無滑鏡動畫），所以每一台的落點幀都是一個獨立鏡位；世界座標由星座重認
或邊界重認解出，這裡只負責「解出來之後怎麼記、怎麼查、下一台挑誰」。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from ggge_ai.runtime import board
from ggge_ai.runtime.coverage import WorldGrid
from ggge_ai.runtime.device import blocked_for_map_tap

Point = tuple[float, float]
Cell = tuple[int, int]
Region = tuple[int, int, int, int]
Key = tuple[str, int]

SCREEN_CENTRE: Point = (1170.0, 540.0)

SOURCE_CONSTELLATION = "constellation"
SOURCE_BORDER = "border"
UNRESOLVED = "unresolved"

# 我方跳轉會進入「單位移動」行動模式，解除只能點右下「返回」；移動格點下去是真的
# 下移動指令。返回鈕帶自己的 intent 過危險帶（見 device.DANGER_BANDS）。
ALLY_DISMISS_TAP: tuple[int, int] = (1798, 971)
ALLY_DISMISS_INTENT = "ally_dismiss"

# 共現複核的容差：另一台單位的格心投影到本窗，附近要真的有一個密度峰。
CO_SIGHTING_PITCH = 0.6

# 疊在地圖上層的 UI：這些矩形底下的「格」點不到，點下去命中的是 UI。0806 實機
# run 挑到 (2238,1011) 撞上 device 的 weapon_dial 帶才發現——空白格挑選原本完全
# 沒有覆蓋區概念，而它專挑離畫面中心最遠的格，等於專挑四角的 UI。
# 矩形量自 assets/screenshots/20260806-013329.png（敵方指定中）與 20260806-013000.png
# （我方回合地圖），(x, y, w, h) 螢幕座標，各邊留了一格餘裕。
UI_EXCLUSION_ZONES: tuple[Region, ...] = (
    # 頂部狀態帶：回合旗／TURN／破壞數／勝利條件字樣，橫貫全寬。
    (0, 0, 2340, 130),
    # 右上 AUTO ＋快進 ＋☰。
    (1700, 0, 640, 140),
    # 左上單位資訊卡：跳轉到某一台之後這裡會長出駕駛員／HP／EN 兩張卡。
    (140, 120, 840, 180),
    # 左側「回合結束」與「變更初期配置」兩顆鈕（對齊 device 的同名危險帶）。
    (140, 130, 320, 210),
    # 左下訊息列。
    (0, 940, 1560, 140),
    # 右下「單位列表」鈕：點下去會展開卡條，之後每一幀的 find_units 都被污染。
    (1740, 930, 600, 150),
)


def in_ui_zone(point: Point, zones: Sequence[Region] = UI_EXCLUSION_ZONES) -> bool:
    return any(x <= point[0] <= x + w and y <= point[1] <= y + h for x, y, w, h in zones)


@dataclass(frozen=True)
class Jump:
    """一台單位的落點記帳：世界格、解出它的證人、當時鏡位與同窗看到的峰。"""

    key: Key
    cell: Cell
    source: str
    offset: Point
    peaks: tuple[Point, ...] = ()


@dataclass(frozen=True)
class Contradiction:
    seen_from: Key
    about: Key
    expected: Point
    nearest: float | None


@dataclass
class JumpLedger:
    """逐台的座標帳。解不出來的留在 failures，排程照樣看得到它還沒解。"""

    jumps: dict[Key, Jump] = field(default_factory=dict)
    failures: dict[Key, int] = field(default_factory=dict)
    candidates: dict[Key, tuple[Cell, ...]] = field(default_factory=dict)

    def record(self, jump: Jump) -> None:
        self.jumps[jump.key] = jump
        self.failures.pop(jump.key, None)

    def fail(self, key: Key) -> int:
        self.failures[key] = self.failures.get(key, 0) + 1
        return self.failures[key]

    def hint(self, key: Key, cells: Iterable[Cell]) -> None:
        """把「某個已解視窗裡看到、還沒有人認領」的格掛給某一台當候選。"""
        self.candidates[key] = tuple(dict.fromkeys(cells))

    def resolved(self, key: Key) -> bool:
        return key in self.jumps

    def cells(self) -> tuple[Cell, ...]:
        return tuple(jump.cell for jump in self.jumps.values())

    def references(self) -> tuple[Cell, ...]:
        """星座重認的參考集：本模組自帳的已解格，不借 sweep 的確認帳。"""
        return tuple(dict.fromkeys(self.cells()))


def target_peak(peaks: Sequence[Point], centre: Point = SCREEN_CENTRE) -> Point | None:
    """跳轉把目標帶到接近畫面中心，所以離中心最近的那個峰就是目標。"""
    if not peaks:
        return None
    return min(peaks, key=lambda peak: (peak[0] - centre[0]) ** 2 + (peak[1] - centre[1]) ** 2)


def world_cells(grid: WorldGrid, offset: Point, peaks: Iterable[Point]) -> tuple[Cell, ...]:
    return tuple(grid.cell_of((peak[0] + offset[0], peak[1] + offset[1])) for peak in peaks)


def next_target(
    ledger: JumpLedger,
    roster: Sequence[Key],
    *,
    give_up_after: int = 2,
) -> Key | None:
    """樹狀機會主義：先挑手上已經有候選格的未解單位（落點必定看得到已解單位，
    星座重認才立得住），其次挑敗過最少次的，同分照名冊順序。

    「敗過最少次的優先」就是開機保護：第一台跳過去時參考集是空的，星座必然解不出，
    而**換一台就換一個落點**——原地重試同一台是把同一個死局再跑一次，先把整份名冊
    輪過一遍才有機會撞上看得見界線的那一台。
    """
    pending = [
        key
        for key in roster
        if not ledger.resolved(key) and ledger.failures.get(key, 0) < give_up_after
    ]
    if not pending:
        return None
    return min(
        pending,
        key=lambda key: (0 if ledger.candidates.get(key) else 1, ledger.failures.get(key, 0)),
    )


def audit(
    ledger: JumpLedger,
    grid: WorldGrid,
    *,
    region: Region = board.UNIT_DENSITY_REGION,
    tolerance: float = CO_SIGHTING_PITCH,
) -> list[Contradiction]:
    """共現對逐對複核：B 的最終世界格投影回 A 的窗裡，那裡就該有一個峰。

    投影落在窗外的對子不算共現，跳過；落在窗內卻沒有峰＝兩台至少有一台的格是錯的。
    """
    span = tolerance * max(grid.col_pitch, grid.row_pitch)
    x, y, w, h = region
    out: list[Contradiction] = []
    for seen_from, host in ledger.jumps.items():
        for about, guest in ledger.jumps.items():
            if seen_from == about:
                continue
            centre = grid.centre_of(guest.cell)
            expected = (centre[0] - host.offset[0], centre[1] - host.offset[1])
            if not (x <= expected[0] <= x + w and y <= expected[1] <= y + h):
                continue
            nearest = min(
                (
                    float(np.hypot(peak[0] - expected[0], peak[1] - expected[1]))
                    for peak in host.peaks
                ),
                default=None,
            )
            if nearest is None or nearest > span:
                out.append(Contradiction(seen_from, about, expected, nearest))
    return out


# 敵方跳轉後畫面留著紅圈指定與紅色攻擊範圍格，點任一個「不是峰、也不是紅格」的
# 格心就解除，鏡頭留在原地。紅格用格內紅色像素佔比判，不吃 battle/vision 的門檻表。
RED_CELL_FRACTION = 0.12
PEAK_KEEP_OUT_PITCH = 0.9


def red_fraction(frame: np.ndarray, centre: Point, half: float) -> float:
    x0, y0 = max(int(centre[0] - half), 0), max(int(centre[1] - half), 0)
    patch = frame[y0 : y0 + int(half * 2), x0 : x0 + int(half * 2)]
    if patch.size == 0:
        return 1.0
    pixels = patch.reshape(-1, 3).astype(np.float32)
    blue, green, red = pixels[:, 0], pixels[:, 1], pixels[:, 2]
    return float(((red > 90) & (red > blue + 30) & (red > green + 30)).mean())


def blank_cell_tap(
    frame: np.ndarray,
    grid: WorldGrid,
    offset: Point,
    peaks: Sequence[Point],
    *,
    region: Region = board.UNIT_DENSITY_REGION,
    red_max: float = RED_CELL_FRACTION,
    zones: Sequence[Region] = UI_EXCLUSION_ZONES,
    blocked: Callable[[Point], bool] = blocked_for_map_tap,
) -> tuple[int, int] | None:
    """解除敵方指定用的空白格：窗內離畫面中心最遠的乾淨格（離峰遠、不紅、不在 UI 底下）。

    挑最遠的是為了離目標與它的攻擊範圍越遠越好——貼著目標點下去等於在紅格裡賭；
    但「最遠」天生指向四角，所以 UI 遮罩要在算距離之前先濾掉。
    """
    x, y, w, h = region
    keep_out = PEAK_KEEP_OUT_PITCH * max(grid.col_pitch, grid.row_pitch)
    half = min(grid.col_pitch, grid.row_pitch) / 3.0
    first = grid.cell_of((x + offset[0], y + offset[1]))
    last = grid.cell_of((x + w + offset[0], y + h + offset[1]))
    best: tuple[float, tuple[int, int]] | None = None
    for col in range(first[0], last[0] + 1):
        for row in range(first[1], last[1] + 1):
            centre = grid.centre_of((col, row))
            point = (centre[0] - offset[0], centre[1] - offset[1])
            if not (x <= point[0] <= x + w and y <= point[1] <= y + h):
                continue
            if any(
                abs(peak[0] - point[0]) <= keep_out and abs(peak[1] - point[1]) <= keep_out
                for peak in peaks
            ):
                continue
            if in_ui_zone(point, zones) or blocked(point):
                continue
            if red_fraction(frame, point, half) >= red_max:
                continue
            score = float(np.hypot(point[0] - SCREEN_CENTRE[0], point[1] - SCREEN_CENTRE[1]))
            if best is None or score > best[0]:
                best = (score, (int(round(point[0])), int(round(point[1]))))
    return None if best is None else best[1]


def ledger_report(ledger: JumpLedger, roster: Sequence[Key]) -> list[Mapping[str, object]]:
    """最終座標帳：cell=[x,y]，0 起算西北原點（對齊 assets/stage_truth 慣例）。"""
    out: list[Mapping[str, object]] = []
    for faction, index in roster:
        jump = ledger.jumps.get((faction, index))
        out.append(
            {
                "faction": faction,
                "index": index,
                "cell": None if jump is None else [jump.cell[0], jump.cell[1]],
                "source": UNRESOLVED if jump is None else jump.source,
            }
        )
    return out
