"""實機截圖 fixture 的載入器。

裁片是原解析度存的，載入時貼回空白畫布的原始位置——絕對座標的區域與探針才對得
上（同 test_vision_regression 的做法）。
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent / "vision"
CANVAS = (1080, 2340)


def path_of(case: str) -> Path:
    for suffix in (".png", ".jpg"):
        candidate = ROOT / f"{case}{suffix}"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"no fixture image for {case}")


@functools.cache
def load(case: str) -> np.ndarray:
    """一張完整畫面（2340x1080）。裁片按 .json 的 box 貼回原位。"""
    image = cv2.imread(str(path_of(case)))
    assert image is not None, case
    if image.shape[:2] == CANVAS:
        return image
    meta = ROOT / f"{case}.json"
    if not meta.exists():
        raise AssertionError(f"{case} is a crop with no box metadata")
    x, y, _, _ = json.loads(meta.read_text(encoding="utf-8"))["box"]
    canvas = np.zeros((*CANVAS, 3), np.uint8)
    canvas[y : y + image.shape[0], x : x + image.shape[1]] = image
    return canvas


def paste(image: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    x, y, _, _ = box
    canvas = np.zeros((*CANVAS, 3), np.uint8)
    canvas[y : y + image.shape[0], x : x + image.shape[1]] = image
    return canvas
