"""內層門面：戰術定價的介面契約。實作是批 1b 的 expectiminimax。

保守下界語意：交戰結果是分布，計價可以把風險折進 cost，但 guarantee
只在「無論擲骰如何都成立」時才給——所以只有必殺才是 KILL。規劃層據此
推狀態，多賺的靠重規劃收割。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class Guarantee(Enum):
    NONE = "none"
    KILL = "kill"


class Verdict(Enum):
    PURSUE = "pursue"
    WITHDRAW = "withdraw"


@dataclass(frozen=True)
class Pricing:
    """cost 是非負的計畫邊權；負值會讓 A* 的封閉集失效，規劃層拒收。"""

    cost: float
    guarantee: Guarantee = Guarantee.NONE
    note: str = ""


@dataclass(frozen=True)
class Appraisal:
    verdict: Verdict
    reason: str = ""


class Advisor[StateT, ActionT](Protocol):
    """符號狀態與候選行動進，建議與計價出。

    price 回傳與 candidates 等長、逐位對齊的序列；None ＝ 不背書，
    規劃層直接把該候選踢出搜尋，不自行補價。
    """

    def appraise(self, state: StateT) -> Appraisal: ...

    def price(self, state: StateT, candidates: Sequence[ActionT]) -> Sequence[Pricing | None]: ...
