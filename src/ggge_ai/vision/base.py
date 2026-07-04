from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ..perception.base import Bbox, ScreenId, UiElement

Image = np.ndarray  # BGR, as produced by OpenCV


@dataclass
class ScreenCandidate:
    screen: ScreenId
    confidence: float


@dataclass
class TextResult:
    text: str
    confidence: float
    bbox: Bbox | None = None


class Recognizer(Protocol):
    """A single recognition backend. Unsupported capabilities return empty results."""

    name: str

    def classify_screen(self, img: Image) -> list[ScreenCandidate]: ...

    def detect_elements(self, img: Image, element_ids: Sequence[str]) -> list[UiElement]: ...

    def read_text(self, img: Image, region: Bbox | None = None) -> list[TextResult]: ...
