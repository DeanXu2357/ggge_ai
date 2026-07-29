"""行動詞彙（移動／攻擊／待機／應戰／主動離開…）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Action:
    """批 0 只有識別名；前置與效果的形狀留給批 1 的行動詞彙最小集。"""

    name: str


CATALOG: tuple[Action, ...] = ()
