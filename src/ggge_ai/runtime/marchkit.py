"""推鏡與標記的共用機制：**逐段搬自 `scripts/sweep_scan.py`**（十二輪實戰驗證）。

搬運原則：邏輯與常數以 `sweep_scan.py` 為準，只做「腳本層 → 模組層」的介面整理
（device／camera／journal／sleep 依賴注入），每一段都在 docstring 第一行註明它對應
`sweep_scan` 的哪個函式。行為差異只有一處，寫在 `Marcher.pan` 的說明裡。

`sweep_scan` 那些吃 `SweepLedger`／`offset` 世界模型的部分（`frontier_tap` 的候選挑選、
`at_border` 的帳本佐證、`anchor_on_marker` 的世界重錨）**沒有搬**：它們的證據來自那支
腳本自己的世界帳，換一個呼叫端就沒有對應物。候選要點哪一格由呼叫端決定，這裡只負責
「點下去算不算數」與「推鏡有沒有生效」這兩件跨腳本共通的紀律。
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from ggge_ai.runtime import board, sweep

Point = tuple[float, float]

# 推鏡連吃這麼多把就別再對著吞點空轉（sweep.GESTURE_EATEN_LIMIT）。
PAN_BORDER = "border"


class Camera(Protocol):
    def grab(self) -> np.ndarray: ...


@dataclass(frozen=True)
class PanResult:
    """一把推鏡的結果：實際打出去的行程、驗收幀、裁決。

    `frame` 是 swipe 之後 `PAN_SETTLE_S` ＋一次 screencap 往返才取的那一張，呼叫端
    直接拿去用——再拍一次只是多付截圖錢（`sweep_scan.pan` 的原註解）。
    """

    stroke: float
    frame: np.ndarray
    verdict: str
    attempts: int


@dataclass(frozen=True)
class MarkerPlacement:
    """一次種標記的驗收結果（`sweep_scan.carry_marker` 的驗收段）。"""

    verdict: str
    signature: board.MarkerSignature | None
    point: Point | None

    @property
    def ok(self) -> bool:
        return self.verdict == sweep.TAP_EMPTY


@dataclass
class Marcher:
    """推鏡與標記的執行者。世界帳不在這裡——它只回報「發生了什麼」。"""

    device: Any
    camera: Camera
    journal: Any
    sleep: Callable[[float], None] = time.sleep
    signature: board.MarkerSignature | None = None
    pinned: set[str] = field(default_factory=set)

    # ---------- 標記 ----------

    def marker_point(self, frame: np.ndarray) -> Point | None:
        """← `sweep_scan.marker_point`：填色標記在這一幀的螢幕位置。

        推鏡前後各問一次就是**未包裝的真實位移**——手勢名義行程不是證人。
        """
        if self.signature is None:
            return None
        return board.find_marker(frame, self.signature, holes=board.UNIT_DENSITY_HUD_HOLES)

    def marker_gone(self, frame: np.ndarray) -> bool:
        """← `sweep_scan.drop_stale_marker` 的判準：記著的標記在這一幀看不見＝它已經沒了。

        看不見還拿它當證人，下一次重認就是拿舊填色配新格號，整幀寫進差一格距整數倍的
        位置（20260805-144856 第 114 序種下的標記到第 124 序已經不在畫面上，之後十圈
        都沒再種過）。
        """
        if self.signature is None:
            return True
        gone = self.marker_point(frame) is None
        if gone:
            self.journal.record("marker_stale")
        return gone

    def place_marker(
        self,
        point: Point,
        frame: np.ndarray,
        *,
        pitch: tuple[float, float],
        card: Callable[[np.ndarray], bool],
        signature: board.MarkerSignature | None = None,
        settle: float = 0.8,
    ) -> MarkerPlacement:
        """← `sweep_scan.carry_marker` 的驗收段：點一格種標記，**驗收填色真的出現在那一格**。

        點擊生效與手勢生效同一條紀律：發出≠生效。`sweep.classify_tap` 只有在填色確實
        出現在被點的那一格才回 `TAP_EMPTY`，所以驗收就是它；沒驗過就更新標記會讓下一次
        重認拿舊填色配新格號。說不出結果的那一下（`TAP_NONE`）**重拍重點一次**再判——
        `sweep_scan` 的 `carry_failed` 就是這一步。
        """
        outcome = self._tap_once(point, frame, pitch=pitch, card=card, signature=signature,
                                 settle=settle)
        if outcome.verdict == sweep.TAP_NONE:
            self.journal.record("carry_failed", point=[round(v, 1) for v in point])
            outcome = self._tap_once(point, self.camera.grab(), pitch=pitch, card=card,
                                     signature=signature, settle=settle)
        learned = outcome.learned or signature
        self.journal.record(
            "place_marker", point=[round(v, 1) for v in point], verdict=outcome.verdict
        )
        if outcome.verdict != sweep.TAP_EMPTY or learned is None:
            return MarkerPlacement(outcome.verdict, None, outcome.marker)
        self.signature = learned
        return MarkerPlacement(outcome.verdict, learned, outcome.marker or point)

    def _tap_once(
        self,
        point: Point,
        before: np.ndarray,
        *,
        pitch: tuple[float, float],
        card: Callable[[np.ndarray], bool],
        signature: board.MarkerSignature | None,
        settle: float,
    ) -> sweep.TapOutcome:
        self.device.tap(int(point[0]), int(point[1]))
        self.sleep(settle)
        after = self.camera.grab()
        return sweep.classify_tap(
            before, after, point, signature=signature, card=card, pitch=pitch
        )

    # ---------- 推鏡 ----------

    def stride(self, spot: Point | None, direction: str, pitch: float, reach: float) -> float:
        """← `sweep_scan.stride`：想要的步幅，被「推完標記仍在新窗視野內」的硬上限夾住。"""
        if spot is None:
            return max(board.PAN_MIN_REACH, min(reach, board.PAN_MAX_REACH))
        cap = sweep.stride_cap(spot, direction, margin=sweep.MARKER_KEEP_PITCH * pitch)
        return max(board.PAN_MIN_REACH, min(reach, board.PAN_MAX_REACH, cap))

    def pan(
        self, direction: str, frame: np.ndarray, reach: float | None = None
    ) -> PanResult:
        """← `sweep_scan.pan`：一把推鏡，**逐手勢驗收行程**。

        發出去的手勢不等於生效的手勢：省電觸控鎖會無聲吞掉整把。沒生效就先做解鎖檢查
        （`device.ensure_unlocked(force=True)`）再把同一把原樣重發；連吃就停手，不再對著
        吞點空轉。行程由標記像素位移驗收（未包裝），相位只在標記看不見時撐場——所以行程
        先過 `legible_reach`，把相位殘量調離 0，免得走了一整把讀起來像沒動。

        **唯一的行為差異**：`sweep_scan` 連吃到上限是 `raise Halt`，這裡改回
        `verdict=sweep.PAN_EATEN` 交給呼叫端裁決（掃描腳本要換下一台，不是整輪停手）。
        要原本的語意，呼叫端看到 `PAN_EATEN` 自己 Halt 即可。

        夾停（`PAN_PINNED`）與見界一律回行程 0：推不動**永遠不等於**有界線，界線由呼叫端
        自己的證據說了算，這裡只把當下看得見的終止邊記進流水帳。
        """
        wanted = board.PAN_MAX_REACH if reach is None else reach
        origin, stroke = board.pan_stroke(direction, wanted, board.find_sightings(frame))
        seen = board.lattice_phase(frame)
        if seen is not None:
            stroke = board.legible_reach(direction, stroke, seen[1])
        x1, y1, x2, y2 = board.pan_gesture(direction, origin, stroke)
        pinned = 0
        before = seen
        for attempt in range(sweep.GESTURE_EATEN_LIMIT):
            was = self.marker_point(frame)
            self.device.swipe(x1, y1, x2, y2, board.PAN_DURATION_S)
            self.sleep(board.PAN_SETTLE_S)
            frame = self.camera.grab()
            after = board.lattice_phase(frame)
            shift = (
                None
                if before is None or after is None
                else board.phase_shift(before[0], after[0], before[1])
            )
            before = after
            now = self.marker_point(frame)
            moved = None if was is None or now is None else (now[0] - was[0], now[1] - was[1])
            verdict = sweep.gesture_verdict(
                shift, direction, travel=stroke * board.PAN_GAIN, moved=moved
            )
            self.journal.record(
                "pan",
                direction=direction,
                origin=[round(v, 1) for v in origin],
                reach=round(stroke, 1),
                attempt=attempt,
                verdict=verdict,
                phase=None if shift is None else [round(v, 1) for v in shift],
                moved=None if moved is None else [round(v, 1) for v in moved],
            )
            if verdict == sweep.PAN_LANDED:
                self.pinned.discard(direction)
                return PanResult(stroke, frame, verdict, attempt + 1)
            borders = sweep.read_borders(frame)
            if direction in borders:
                self.journal.record(
                    "pan_exhausted",
                    direction=direction,
                    attempt=attempt,
                    borders=sorted(borders),
                )
                return PanResult(0.0, frame, PAN_BORDER, attempt + 1)
            if verdict == sweep.PAN_PINNED:
                pinned += 1
                if pinned >= sweep.GESTURE_PINNED_LIMIT:
                    self.pinned.add(direction)
                    self.journal.record(
                        "pan_pinned",
                        direction=direction,
                        attempt=attempt,
                        borders=sorted(borders),
                    )
                    return PanResult(0.0, frame, sweep.PAN_PINNED, attempt + 1)
                continue
            # 被吃：先做解鎖檢查再把同一把原樣重發（省電觸控鎖會無聲吞掉整把）。
            self.journal.record("pan_retry", direction=direction, attempt=attempt)
            self.device.ensure_unlocked(force=True)
        return PanResult(stroke, frame, sweep.PAN_EATEN, sweep.GESTURE_EATEN_LIMIT)


def visible_borders(frame: np.ndarray) -> Mapping[str, float]:
    """← `sweep_scan` 一路在用的 `sweep.read_borders`：這一幀目視到的終止邊。"""
    return sweep.read_borders(frame)
