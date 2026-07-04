from __future__ import annotations

import time
from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np

from ...vision.pipeline import RecognizerPipeline
from ..base import UNKNOWN_SCREEN, GameState, UiElement


class AdbPerception:
    """Captures screenshots via uiautomator2 and delegates recognition to the
    vision pipeline. element_ids_by_screen declares which elements are worth
    looking for on each screen."""

    def __init__(
        self,
        device,
        pipeline: RecognizerPipeline,
        element_ids_by_screen: dict[str, Sequence[str]] | None = None,
        screenshot_dir: Path | None = None,
    ) -> None:
        self.device = device
        self.pipeline = pipeline
        self.element_ids_by_screen = element_ids_by_screen or {}
        self.screenshot_dir = screenshot_dir

    def observe(self) -> GameState:
        img = self._capture()
        screenshot_path = self._save(img)

        candidate = self.pipeline.classify_screen(img)
        if candidate is None:
            return GameState(
                screen=UNKNOWN_SCREEN, screen_confidence=0.0, screenshot_path=screenshot_path
            )

        element_ids = self.element_ids_by_screen.get(candidate.screen, ())
        elements = self.pipeline.detect_elements(img, element_ids) if element_ids else []
        return GameState(
            screen=candidate.screen,
            screen_confidence=candidate.confidence,
            elements=elements,
            screenshot_path=screenshot_path,
        )

    def capture(self) -> np.ndarray:
        """Raw BGR screenshot; used for motion detection between frames."""
        return self._capture()

    def probe(self, element_ids: Sequence[str]) -> dict[str, UiElement]:
        """Fresh capture, detect the given elements regardless of current
        screen. Lets flow actions look for buttons (download popup, AUTO
        state) that are not tied to a classified screen."""
        img = self._capture()
        return {e.id: e for e in self.pipeline.detect_elements(img, element_ids)}

    def _capture(self) -> np.ndarray:
        pil_img = self.device.screenshot()
        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    def _save(self, img: np.ndarray) -> Path | None:
        if self.screenshot_dir is None:
            return None
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        path = self.screenshot_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 1000}.png"
        cv2.imwrite(str(path), img)
        return path
