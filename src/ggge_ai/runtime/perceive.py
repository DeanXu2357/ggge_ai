"""畫面分類與讀數（吃實機標定成果：模板、座標）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..contracts import Ending


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


class LivePerceiver:
    def look(self) -> Observation[Any]:
        raise NotImplementedError("批 2：內層實機首戰")


def classify(frame: Any) -> str:
    raise NotImplementedError("批 2：內層實機首戰")


def read(frame: Any) -> dict[str, Any]:
    raise NotImplementedError("批 2：內層實機首戰")
