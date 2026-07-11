from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ..perception.base import Bbox, ScreenId, UiElement
from .base import Image, ScreenCandidate, TextResult


def _highpass(img: Image) -> Image:
    """Local-mean removal: keeps glyph strokes, drops the background
    brightness offset. Fixes TM_CCOEFF_NORMED degrading when a template
    captured on a dark map is matched over a bright one (snowfield labels
    measured 0.764 raw vs 0.893 highpass, dark maps stay 0.96+); do not
    enable it on templates whose meaning depends on brightness (keyguard)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    blur = cv2.GaussianBlur(gray, (31, 31), 0)
    return np.clip(gray - blur + 128, 0, 255).astype(np.uint8)


PREPROCESSORS = {"highpass": _highpass}


@dataclass
class Template:
    id: str
    image: Image
    search_region: Bbox | None = None
    preprocess: str | None = None


def load_template(
    id: str,
    path: Path,
    search_region: Bbox | None = None,
    preprocess: str | None = None,
) -> Template:
    img = cv2.imread(str(path))
    if img is None:
        raise FileNotFoundError(f"template image not readable: {path}")
    if preprocess is not None and preprocess not in PREPROCESSORS:
        raise ValueError(f"unknown preprocess {preprocess!r} for template {id}")
    return Template(id=id, image=img, search_region=search_region, preprocess=preprocess)


class TemplateRecognizer:
    """OpenCV template matching against pre-cropped anchor/button images.

    screen_anchors maps ScreenId to the anchor template that uniquely
    identifies that screen; element_templates maps element id to its template.
    """

    name = "template"

    def __init__(
        self,
        screen_anchors: dict[ScreenId, Template] | None = None,
        element_templates: dict[str, Template] | None = None,
    ) -> None:
        self.screen_anchors = screen_anchors or {}
        self.element_templates = element_templates or {}

    def classify_screen(self, img: Image) -> list[ScreenCandidate]:
        candidates = []
        for screen, template in self.screen_anchors.items():
            score, _ = self._match(img, template)
            candidates.append(ScreenCandidate(screen=screen, confidence=score))
        candidates.sort(key=lambda c: c.confidence, reverse=True)
        return candidates

    def detect_elements(self, img: Image, element_ids: Sequence[str]) -> list[UiElement]:
        elements = []
        for eid in element_ids:
            template = self.element_templates.get(eid)
            if template is None:
                continue
            score, bbox = self._match(img, template)
            elements.append(UiElement(id=eid, bbox=bbox, confidence=score))
        return elements

    def read_text(self, img: Image, region: Bbox | None = None) -> list[TextResult]:
        return []

    def _match(self, img: Image, template: Template) -> tuple[float, Bbox]:
        region = template.search_region
        offset_x, offset_y = 0, 0
        haystack = img
        if region is not None:
            haystack = img[region.y : region.y + region.h, region.x : region.x + region.w]
            offset_x, offset_y = region.x, region.y
        needle = template.image
        if template.preprocess is not None:
            preprocess = PREPROCESSORS[template.preprocess]
            haystack = preprocess(haystack)
            needle = preprocess(needle)
        result = cv2.matchTemplate(haystack, needle, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        th, tw = template.image.shape[:2]
        bbox = Bbox(x=max_loc[0] + offset_x, y=max_loc[1] + offset_y, w=tw, h=th)
        return float(max_val), bbox
