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
SOURCE_CHAIN = "chain"
UNRESOLVED = "unresolved"

MATCH_OK = "ok"
MATCH_AMBIGUOUS = "ambiguous"
MATCH_NO_MATCH = "no_match"
MATCH_FEW_PEAKS = "few_peaks"

# 判別式是「比例＋領先差」，不是固定的共同峰數。固定門檻跨輪不穩：run
# 20260806-042858 用門檻 2 長出 31 條邊、環一致性撞出 8 筆矛盾，門檻 3 才歸零；但同一
# 個 3 到了 run 20260806-052235 又把好邊砍掉一半（9 條，最大元件 6），而該輪門檻 2 的
# 15 條邊一筆矛盾都沒有。安全值逐輪不同＝這個量本來就不是判別依據。
# 改成：重疊區內覆蓋率 ≥ 0.8、最優解的命中數領先次優 ≥ 2、命中數 ≥ 3。唯一性語意沒
# 有放寬——領先差就是唯一性，只是從「不准有第二解」變成「第二解要明顯更差」。
PATTERN_MIN_OVERLAP = 3
PATTERN_MIN_COVERAGE = 0.8
PATTERN_MIN_LEAD = 2
# 重疊區四邊各丟掉一格：窗邊的單位在另一窗只露半身，峰時有時無。
PATTERN_EDGE_MARGIN = 1

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
class Pattern:
    """一窗的相對圖樣：窗內每個峰相對**目標峰**的整數格差，含目標自己的 (0,0)。

    用落點幀自己的格線相位算，所以完全不需要世界 offset——這正是它能在「一台都還
    沒定位」的時候就開始長鏈的原因（0806 run 20260806-042858：48 筆 lost 全是
    constellation few_units，絕對解的參考集永遠湊不滿，鏈起不了頭）。
    """

    cells: tuple[Cell, ...]
    # 這一窗看得到的格範圍（同樣相對目標）。重疊區要用窗算，不能用峰的外框——
    # 峰的外框是「偵測到什麼」，窗才是「看得到哪裡」，拿前者當重疊區會把「這一格
    # 在窗外所以沒峰」誤判成「這一格該有峰卻沒有」。
    window: tuple[int, int, int, int]


@dataclass(frozen=True)
class PatternMatch:
    """兩窗配對的結果：delta＝窗 b 的目標相對窗 a 的目標的整數格差。"""

    delta: Cell | None
    overlap: int
    reason: str


@dataclass(frozen=True)
class ChainEdge:
    """一條鏈邊：to 的世界格 ＝ frm 的世界格 ＋ delta。"""

    frm: Key
    to: Key
    delta: Cell
    overlap: int


@dataclass(frozen=True)
class AxisAnchor:
    """單軸絕對值：某一台在世界座標上的絕對行或列。

    單窗同時解出兩軸太苛（0806 run 20260806-052235 全場 0 個雙軸錨，border 常常只
    給得出 ['x']——西界常入鏡、北界很少）。單軸照樣是硬證據：鏈把整個元件綁成一
    塊剛體之後，元件裡**任何一台**的 x 就定得了全元件的 x，y 可以來自另一台。
    """

    key: Key
    axis: int
    value: int


@dataclass(frozen=True)
class AxisConflict:
    key: Key
    axis: int
    known: int
    saw: int


@dataclass(frozen=True)
class ChainConflict:
    """同一台由兩條路徑到達的格不一致。記下來，不覆寫任何一邊。"""

    key: Key
    known: Cell
    saw: Cell
    via: Key


AXIS_NAMES = ("x", "y")


@dataclass(frozen=True)
class ChainSolution:
    """鏈的結算：元件內的相對格 ＋ 每個元件逐軸的全域平移。

    平移只有在該元件該軸拿得到絕對值時才有；拿不到就是拿不到，相對格照樣有用。
    """

    cells: dict[Key, Cell]
    components: dict[Key, int]
    shifts: dict[int, dict[int, int]]
    linked: frozenset[Key]
    conflicts: tuple[ChainConflict, ...]
    axis_conflicts: tuple[AxisConflict, ...]

    def axes(self, key: Key) -> tuple[str, ...]:
        shift = self.shifts.get(self.components.get(key, -1), {})
        return tuple(AXIS_NAMES[axis] for axis in sorted(shift))

    def world(self, key: Key) -> tuple[int | None, int | None]:
        cell = self.cells.get(key)
        if cell is None:
            return (None, None)
        shift = self.shifts.get(self.components.get(key, -1), {})
        return tuple(  # type: ignore[return-value]
            None if axis not in shift else cell[axis] + shift[axis] for axis in (0, 1)
        )

    def anchored(self, key: Key) -> bool:
        return all(value is not None for value in self.world(key))

    @property
    def any_anchor(self) -> bool:
        return any(shift for shift in self.shifts.values())


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
    patterns: dict[Key, Pattern] = field(default_factory=dict)
    edges: list[ChainEdge] = field(default_factory=list)
    axis_anchors: list[AxisAnchor] = field(default_factory=list)

    def record(self, jump: Jump) -> None:
        self.jumps[jump.key] = jump
        self.failures.pop(jump.key, None)

    def link(
        self,
        key: Key,
        pattern: Pattern,
        *,
        min_overlap: int = PATTERN_MIN_OVERLAP,
    ) -> list[tuple[Key, PatternMatch]]:
        """記下這一窗的圖樣，並與所有既有窗配對。回傳逐窗的配對結果供落帳。

        配對成功的才長邊；ambiguous／no_match 一樣回報，那是給人看的證據不是失敗。
        """
        out: list[tuple[Key, PatternMatch]] = []
        for other, known in self.patterns.items():
            if other == key:
                continue
            found = match_patterns(known, pattern, min_overlap=min_overlap)
            out.append((other, found))
            if found.delta is not None:
                self.edges.append(ChainEdge(other, key, found.delta, found.overlap))
        self.patterns[key] = pattern
        self.failures.pop(key, None)
        return out

    def anchor_axis(self, key: Key, axis: int, value: int) -> None:
        self.axis_anchors.append(AxisAnchor(key, axis, value))
        self.failures.pop(key, None)

    def solve(self) -> ChainSolution:
        """名冊上沒有圖樣的單位不進來——它們是「沒看過」，不是「相對原點」。"""
        anchors = list(self.axis_anchors)
        for key, jump in self.jumps.items():
            anchors.extend((AxisAnchor(key, 0, jump.cell[0]), AxisAnchor(key, 1, jump.cell[1])))
        return propagate(self.edges, anchors, nodes=(*self.patterns, *self.jumps))

    def fail(self, key: Key) -> int:
        self.failures[key] = self.failures.get(key, 0) + 1
        return self.failures[key]

    def hint(self, key: Key, cells: Iterable[Cell]) -> None:
        """把「某個已解視窗裡看到、還沒有人認領」的格掛給某一台當候選。"""
        self.candidates[key] = tuple(dict.fromkeys(cells))

    def resolved(self, key: Key) -> bool:
        """跳過就算解過：圖樣本身就是成果，絕對座標由鏈在結算時補。"""
        return key in self.jumps or key in self.patterns

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


def frame_pattern(cells: Iterable[Cell], target: Cell, window: tuple[int, int, int, int]) -> Pattern:
    """幀內格 → 相對圖樣：全部減掉目標的格，幀座標系就消掉了。

    像素→幀內格的那一步**不在這裡**：固定 pitch 的除法會被縱向透視咬掉一列
    （0806 重放實測列座標 ±1 漂移，整數集合的精確比對全數落空），要走
    `battle.map_grid` 的逐線對格。runtime 不得 import battle（見
    tests/test_package_boundary.py），所以轉換由腳本層做完再餵進來——這也讓這支
    留在純函式。

    目標未必在 cells 裡（它是從落點幀鎖定的，乾淨幀重找可能差一個像素），所以
    (0,0) 一律補進去——目標自己永遠是圖樣的一員。
    """
    origin = {(0, 0)}
    for cell in cells:
        origin.add((cell[0] - target[0], cell[1] - target[1]))
    return Pattern(
        tuple(sorted(origin)),
        (
            window[0] - target[0],
            window[1] - target[1],
            window[2] - target[0],
            window[3] - target[1],
        ),
    )


def _shift(cells: Iterable[Cell], delta: Cell) -> set[Cell]:
    return {(cell[0] + delta[0], cell[1] + delta[1]) for cell in cells}


def _inside(cell: Cell, box: tuple[int, int, int, int]) -> bool:
    return box[0] <= cell[0] <= box[2] and box[1] <= cell[1] <= box[3]


def _shift_box(box: tuple[int, int, int, int], delta: Cell) -> tuple[int, int, int, int]:
    return (box[0] + delta[0], box[1] + delta[1], box[2] + delta[0], box[3] + delta[1])


def _overlap_box(
    a: tuple[int, int, int, int], b: tuple[int, int, int, int], *, margin: int
) -> tuple[int, int, int, int] | None:
    """兩窗相交的那一塊，四邊各內縮 margin。

    內縮是因為窗邊那一圈本來就不可靠：貼著邊的單位在另一窗可能只露半個身子，
    `board.find_units` 的密度峰跟著時有時無，拿它當「該有卻沒有」的證據會把好的
    平移一路否決掉。
    """
    box = (
        max(a[0], b[0]) + margin,
        max(a[1], b[1]) + margin,
        min(a[2], b[2]) - margin,
        min(a[3], b[3]) - margin,
    )
    return None if box[0] > box[2] or box[1] > box[3] else box


def match_patterns(
    a: Pattern,
    b: Pattern,
    *,
    min_overlap: int = PATTERN_MIN_OVERLAP,
    margin: int = PATTERN_EDGE_MARGIN,
    min_coverage: float = PATTERN_MIN_COVERAGE,
    min_lead: int = PATTERN_MIN_LEAD,
) -> PatternMatch:
    """兩窗圖樣的平移配對：回傳「b 的目標落在 a 的座標系哪一格」。

    候選平移只取 a 的峰——b 的目標在 a 的窗裡必定也是一個峰（兩窗看得到彼此才配得
    起來）。每個候選在重疊區（兩窗 window 相交、四邊各內縮 margin）內算覆蓋率
    命中／聯集，過門檻的才是可行解；最優解要領先次優 `min_lead` 個命中才收，不然
    ambiguous 拒收——寧可漏認不可錯認。

    覆蓋率而不是全覆蓋，是因為 `board.find_units` 兩幀給的峰集本身就會差一兩個
    （同一台在一幀有峰、另一幀沒有）；全覆蓋對這種偵測級差異零容忍，實測會把整叢
    我軍的正樣本全部否決掉。
    """
    if len(a.cells) < min_overlap or len(b.cells) < min_overlap:
        return PatternMatch(None, 0, MATCH_FEW_PEAKS)
    mine = set(a.cells)
    scored: list[tuple[int, Cell]] = []
    for delta in a.cells:
        shared = _overlap_box(a.window, _shift_box(b.window, delta), margin=margin)
        if shared is None:
            continue
        here = {cell for cell in mine if _inside(cell, shared)}
        there = {cell for cell in _shift(b.cells, delta) if _inside(cell, shared)}
        union = here | there
        if not union:
            continue
        hit = len(here & there)
        if hit < min_overlap or hit / len(union) < min_coverage:
            continue
        scored.append((hit, delta))
    if not scored:
        return PatternMatch(None, 0, MATCH_NO_MATCH)
    scored.sort(key=lambda found: -found[0])
    best = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0
    if best[0] - second < min_lead:
        return PatternMatch(None, best[0], MATCH_AMBIGUOUS)
    return PatternMatch(best[1], best[0], MATCH_OK)


def propagate(
    edges: Sequence[ChainEdge],
    axis_anchors: Sequence[AxisAnchor] = (),
    *,
    nodes: Sequence[Key] = (),
) -> ChainSolution:
    """鏈邊 → 元件內相對格；單軸絕對值 → 元件的全域平移。

    先把每個連通元件當成一塊剛體排好（元件內第一個節點是 (0,0)），再逐軸把整塊平
    移到世界座標。走到已經有座標的節點時只做一致性檢查——環走一圈回來對不上就記
    矛盾，**不覆寫**（覆寫等於讓最後一條路徑說了算，而我們根本不知道哪一條錯）。
    """
    links: dict[Key, list[tuple[Key, Cell]]] = {}
    for edge in edges:
        links.setdefault(edge.frm, []).append((edge.to, edge.delta))
        links.setdefault(edge.to, []).append((edge.frm, (-edge.delta[0], -edge.delta[1])))
    cells: dict[Key, Cell] = {}
    components: dict[Key, int] = {}
    conflicts: list[ChainConflict] = []
    # 每條邊都是雙向走的，同一個不一致會從兩頭各撞一次；記一次就夠。
    seen: set[frozenset[Key]] = set()
    for root in (*nodes, *links):
        if root in cells:
            continue
        component = len(set(components.values()))
        cells[root] = (0, 0)
        components[root] = component
        queue = [root]
        while queue:
            here = queue.pop(0)
            base = cells[here]
            for there, delta in links.get(here, ()):
                found = (base[0] + delta[0], base[1] + delta[1])
                known = cells.get(there)
                if known is None:
                    cells[there] = found
                    components[there] = component
                    queue.append(there)
                elif known != found and frozenset((here, there)) not in seen:
                    seen.add(frozenset((here, there)))
                    conflicts.append(ChainConflict(there, known, found, here))
    shifts: dict[int, dict[int, int]] = {}
    axis_conflicts: list[AxisConflict] = []
    for anchor in axis_anchors:
        cell = cells.get(anchor.key)
        if cell is None:
            continue
        component = components[anchor.key]
        shift = anchor.value - cell[anchor.axis]
        known = shifts.setdefault(component, {}).get(anchor.axis)
        if known is None:
            shifts[component][anchor.axis] = shift
        elif known != shift:
            axis_conflicts.append(
                AxisConflict(anchor.key, anchor.axis, known + cell[anchor.axis], anchor.value)
            )
    return ChainSolution(
        cells,
        components,
        shifts,
        frozenset(links),
        tuple(conflicts),
        tuple(axis_conflicts),
    )


# 補跳只對「接上鏈且夠大」的元件划算：size<3 的元件補到了也只定得了自己那幾台，
# 而每次補跳都是一趟完整的選單→列表→跳轉→解除。
ANCHOR_COMPONENT_MIN = 3
ANCHOR_ATTEMPTS = 2


def needy_axes(
    solution: ChainSolution, *, min_size: int = ANCHOR_COMPONENT_MIN
) -> list[tuple[int, int]]:
    """還缺絕對錨的（元件, 軸），元件序、軸序。"""
    sizes: dict[int, int] = {}
    for key in solution.linked:
        component = solution.components[key]
        sizes[component] = sizes.get(component, 0) + 1
    out: list[tuple[int, int]] = []
    for component, size in sorted(sizes.items()):
        if size < min_size:
            continue
        shift = solution.shifts.get(component, {})
        out.extend((component, axis) for axis in (0, 1) if axis not in shift)
    return out


def axis_frontier(
    solution: ChainSolution,
    component: int,
    axis: int,
    *,
    roster: Sequence[Key] = (),
    limit: int = ANCHOR_ATTEMPTS,
) -> tuple[Key, ...]:
    """元件裡該軸相對座標最小的前 limit 台——缺 y 就挑最靠北的、缺 x 挑最靠西的。

    跳轉會把目標帶到畫面中心，所以跳最邊緣那台最有機會把那一側的界拉進畫面。
    並列取名冊序小者（名冊序就是巡迴序，先跳到的先用）。
    """
    order = {key: index for index, key in enumerate(roster)}
    members = [
        key
        for key in solution.linked
        if solution.components.get(key) == component and key in solution.cells
    ]
    members.sort(key=lambda key: (solution.cells[key][axis], order.get(key, len(order)), key))
    return tuple(members[:limit])


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
    cells: Mapping[Key, Cell] | None = None,
    region: Region = board.UNIT_DENSITY_REGION,
    tolerance: float = CO_SIGHTING_PITCH,
) -> list[Contradiction]:
    """共現對逐對複核：B 的最終世界格投影回 A 的窗裡，那裡就該有一個峰。

    投影落在窗外的對子不算共現，跳過；落在窗內卻沒有峰＝兩台至少有一台的格是錯的。

    `cells` 給鏈傳播後的座標；投影還是只從有絕對鏡位的窗（`ledger.jumps`）出發——
    沒有 offset 的窗根本不知道自己在世界的哪裡，投影無從算起。
    """
    span = tolerance * max(grid.col_pitch, grid.row_pitch)
    x, y, w, h = region
    out: list[Contradiction] = []
    for seen_from, host in ledger.jumps.items():
        for about, guest in ledger.jumps.items():
            if seen_from == about:
                continue
            guest_cell = guest.cell if cells is None else cells.get(about, guest.cell)
            centre = grid.centre_of(guest_cell)
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
    centres: Iterable[Point],
    peaks: Sequence[Point],
    *,
    keep_out: float,
    red_half: float,
    region: Region = board.UNIT_DENSITY_REGION,
    red_max: float = RED_CELL_FRACTION,
    zones: Sequence[Region] = UI_EXCLUSION_ZONES,
    blocked: Callable[[Point], bool] = blocked_for_map_tap,
) -> tuple[int, int] | None:
    """解除敵方指定用的空白格：窗內離畫面中心最遠的乾淨格（離峰遠、不紅、不在 UI 底下）。

    `centres` 是**這一幀自己的**格心（螢幕像素），由呼叫端用 `battle.map_grid` 的逐線
    格網算——固定 pitch 除法會被縱向透視咬掉一列，挑出來的「格心」其實壓在格線上。

    挑最遠的是為了離目標與它的攻擊範圍越遠越好——貼著目標點下去等於在紅格裡賭；
    但「最遠」天生指向四角，所以 UI 遮罩與危險帶要在算距離之前先濾掉。
    """
    x, y, w, h = region
    best: tuple[float, tuple[int, int]] | None = None
    for point in centres:
        if not (x <= point[0] <= x + w and y <= point[1] <= y + h):
            continue
        if any(
            abs(peak[0] - point[0]) <= keep_out and abs(peak[1] - point[1]) <= keep_out
            for peak in peaks
        ):
            continue
        if in_ui_zone(point, zones) or blocked(point):
            continue
        if red_fraction(frame, point, red_half) >= red_max:
            continue
        score = float(np.hypot(point[0] - SCREEN_CENTRE[0], point[1] - SCREEN_CENTRE[1]))
        if best is None or score > best[0]:
            best = (score, (int(round(point[0])), int(round(point[1]))))
    return None if best is None else best[1]


def ledger_report(
    ledger: JumpLedger,
    roster: Sequence[Key],
    solution: ChainSolution | None = None,
) -> list[Mapping[str, object]]:
    """最終座標帳。誠實三分：沒看過的 unresolved、看過但沒接上鏈的也是 unresolved
    （相對格只對自己成立，寫出來會被當成座標讀），接上鏈的給元件編號與相對格，
    兩軸都錨到才寫絕對 `cell`——只錨到一軸就只在 `anchored_axes` 上說話。
    """
    solution = ledger.solve() if solution is None else solution
    out: list[Mapping[str, object]] = []
    for faction, index in roster:
        key = (faction, index)
        cell = solution.cells.get(key)
        linked = key in solution.linked
        jump = ledger.jumps.get(key)
        if jump is not None:
            source = jump.source
        elif linked and cell is not None:
            source = SOURCE_CHAIN
        else:
            source = UNRESOLVED
        world = solution.world(key)
        out.append(
            {
                "faction": faction,
                "index": index,
                "component": None if not linked else solution.components.get(key),
                "relative_cell": None if not linked or cell is None else [cell[0], cell[1]],
                "cell": None if not solution.anchored(key) else [world[0], world[1]],
                # 單軸絕對值是關於這一台的事實，跟它有沒有接上鏈無關——孤立節點
                # 量到了西界就是量到了，照樣說出來。
                "anchored_axes": list(solution.axes(key)),
                "source": source,
            }
        )
    return out
