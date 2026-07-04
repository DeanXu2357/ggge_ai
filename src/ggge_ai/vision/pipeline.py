from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..perception.base import Bbox, UiElement
from .base import Image, Recognizer, ScreenCandidate, TextResult


@dataclass
class Stage:
    recognizer: Recognizer
    accept_above: float = 0.0


class RecognizerPipeline:
    """Runs recognizers in order; a stage whose best confidence clears its
    accept_above threshold short-circuits the chain, otherwise the overall
    best result across stages wins."""

    def __init__(
        self,
        screen_stages: Sequence[Stage] = (),
        element_stages: Sequence[Stage] = (),
        text_stages: Sequence[Stage] = (),
    ) -> None:
        self.screen_stages = list(screen_stages)
        self.element_stages = list(element_stages)
        self.text_stages = list(text_stages)

    def classify_screen(self, img: Image) -> ScreenCandidate | None:
        best: ScreenCandidate | None = None
        for stage in self.screen_stages:
            candidates = stage.recognizer.classify_screen(img)
            for c in candidates:
                if best is None or c.confidence > best.confidence:
                    best = c
            if best is not None and best.confidence >= stage.accept_above:
                return best
        return best

    def detect_elements(self, img: Image, element_ids: Sequence[str]) -> list[UiElement]:
        found: dict[str, UiElement] = {}
        for stage in self.element_stages:
            missing = [eid for eid in element_ids if eid not in found]
            if not missing:
                break
            for element in stage.recognizer.detect_elements(img, missing):
                if element.confidence >= stage.accept_above:
                    existing = found.get(element.id)
                    if existing is None or element.confidence > existing.confidence:
                        found[element.id] = element
        return list(found.values())

    def read_text(self, img: Image, region: Bbox | None = None) -> list[TextResult]:
        for stage in self.text_stages:
            results = stage.recognizer.read_text(img, region)
            if results and max(r.confidence for r in results) >= stage.accept_above:
                return results
        return []
