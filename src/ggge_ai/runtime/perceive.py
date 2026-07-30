"""畫面分類與讀數（吃實機標定成果：模板、座標）。

一個 tick 一張畫面：look() 截一次圖、解一次碼、讀一輪，之後所有判斷都用同一張
幀。Observation.frame 存的是 screencap 的原生 PNG 位元組（不是解碼後的陣列，也
不重新編碼），流水帳照抄就能離線復現當下看到的東西。

符號讀取（誰在場上、誰還能動）是 stage 層的事，所以 reader 是注入的：runtime
不認識 StageState。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import cv2
import numpy as np

from ..contracts import Ending
from . import board, screens


@dataclass(frozen=True)
class Observation[StateT]:
    """一張畫面的全部所見。state 為 None ＝ 這張畫面推不出符號狀態
    （選單、過場、讀不出來），不是「戰場是空的」。frame ＝ 這張畫面的
    原生解析度 PNG 位元組，供事後歸因；離線假件沒有幀就是 None。"""

    screen: str
    state: StateT | None = None
    terminal: Ending | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    frame: bytes | None = None


class Perceiver[StateT](Protocol):
    """look() ＝ 截一張圖並讀成 Observation；迴圈一個 tick 只呼叫一次，
    所以「一張畫面」的紀律由這個接縫定義。"""

    def look(self) -> Observation[StateT]: ...


TERMINAL_SCREENS: dict[str, Ending] = {
    screens.BATTLE_RESULT: Ending.VICTORY,
    # 主動離場後的畫面與戰敗同一張：終局種類的裁決在迴圈（它才知道是不是自己
    # 走的），感知只負責說「這是收場畫面」。
    screens.BATTLE_DEFEAT: Ending.DEFEAT,
}


def decode(frame: bytes | np.ndarray | None) -> np.ndarray | None:
    """PNG 位元組 → BGR 陣列。已經是陣列就原樣回傳（離線假件走這條）。"""
    if frame is None:
        return None
    if isinstance(frame, np.ndarray):
        return frame
    image = cv2.imdecode(np.frombuffer(frame, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"undecodable frame ({len(frame)} bytes)")
    return image


def classify(frame: Any) -> str:
    return screens.classify(decode(frame))


def read(frame: Any) -> dict[str, Any]:
    """這張幀上讀得出來的小值，全部 JSON 可序列化——流水帳要收得下，反射組
    也只吃這些（像素工作只在這裡發生一次）。"""
    image = decode(frame)
    if image is None:
        return {}
    return {
        "auto": screens.read_auto_switch(image),
        # grid_on 是地圖上的地面真相（讀不讀得出格網），grid_setting 是設定頁
        # 滑塊——盤面掃描的符號前置條件看前者，設定頁流程看後者。
        "grid_on": board.read_lattice(image) is not None,
        "grid_setting": screens.read_grid_setting(image),
        "frame_sig": screens.frame_signature(image),
    }


@dataclass
class LivePerceiver[StateT]:
    device: Any
    reader: Callable[[np.ndarray, str], StateT | None] | None = None
    terminals: dict[str, Ending] = field(default_factory=lambda: dict(TERMINAL_SCREENS))

    def look(self) -> Observation[StateT]:
        raw = self.device.screenshot()
        image = decode(raw)
        screen = screens.classify(image)
        state = None if self.reader is None else self.reader(image, screen)
        return Observation(
            screen=screen,
            state=state,
            terminal=self.terminals.get(screen),
            evidence=read(image),
            frame=raw if isinstance(raw, bytes) else None,
        )
