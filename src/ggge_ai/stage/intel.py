"""情報記錄與回寫 stage 快取。"""

from __future__ import annotations

from pathlib import Path

from ..contracts import IntelDelta


def load(stage: str, cache_root: Path) -> IntelDelta:
    raise NotImplementedError("批 1：內層離線")


def write_back(stage: str, delta: IntelDelta, cache_root: Path) -> None:
    raise NotImplementedError("批 1：內層離線")
