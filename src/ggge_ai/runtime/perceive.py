"""畫面分類與讀數（吃實機標定成果：模板、座標）。"""

from __future__ import annotations

from typing import Any


def classify(frame: Any) -> str:
    raise NotImplementedError("批 1：內層離線")


def read(frame: Any) -> dict[str, Any]:
    raise NotImplementedError("批 1：內層離線")
