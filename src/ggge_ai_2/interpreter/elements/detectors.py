from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from ggge_ai_2.interpreter.elements.auto_key import AUTO_RECT, auto_mode
from ggge_ai_2.interpreter.elements.contract import ElementDetector
from ggge_ai_2.interpreter.elements.fast_forward import FAST_FORWARD_BOX, has_fast_forward
from ggge_ai_2.interpreter.elements.region import Region
from ggge_ai_2.interpreter.elements.round_button import ROUND_CENTER, ROUND_RADII, round_button
from ggge_ai_2.interpreter.elements.tap_to_next import TAP_TO_NEXT_REGION, has_tap_to_next
from ggge_ai_2.interpreter.elements.top_left_title import TITLE_REGION, top_left_title
from ggge_ai_2.interpreter.elements.turn_box import TURN_BOX_REGION, has_turn_box
from ggge_ai_2.interpreter.elements.unit_detail import (
    BLOCK_REGIONS,
    BUTTON_REGIONS,
    has_unit_detail_shape,
    has_unit_detail_title,
)
from ggge_ai_2.interpreter.elements.unit_detail import TITLE_REGION as UNIT_DETAIL_TITLE_REGION
from ggge_ai_2.interpreter.elements.unit_list import UnitListButton, unit_list
from ggge_ai_2.interpreter.phase_cue import TITLE_BAND, phase
from ggge_ai_2.screenmodel.contract import ModelElement, Rect, SeenElement

WIDTH, HEIGHT = 2340, 1080
# The ring of the round button has its radius in heights of the frame.
ROUND_BOX: Region = (
    ROUND_CENTER[0] - ROUND_RADII[1] * HEIGHT / WIDTH,
    ROUND_CENTER[1] - ROUND_RADII[1],
    ROUND_CENTER[0] + ROUND_RADII[1] * HEIGHT / WIDTH,
    ROUND_CENTER[1] + ROUND_RADII[1],
)
TITLE_BAND_REGION: Region = (
    TITLE_BAND[0] / WIDTH,
    TITLE_BAND[1] / HEIGHT,
    TITLE_BAND[2] / WIDTH,
    TITLE_BAND[3] / HEIGHT,
)
# The whole button. The button moves down by 235 px when the card row closes.
UNIT_LIST_BOXES: dict[UnitListButton, Region] = {
    UnitListButton.OPEN: (1798 / WIDTH, 728 / HEIGHT, 2170 / WIDTH, 802 / HEIGHT),
    UnitListButton.CLOSED: (1798 / WIDTH, 963 / HEIGHT, 2170 / WIDTH, 1037 / HEIGHT),
}


def pixel_box(image: np.ndarray, region: Region) -> Rect:
    height, width = image.shape[:2]
    left, top, right, bottom = region
    return int(left * width), int(top * height), int(right * width), int(bottom * height)


@dataclass(frozen=True)
class ShapeDetector:
    element: ModelElement
    region: Region
    present: Callable[[np.ndarray], bool]

    def detect(self, image: np.ndarray) -> Sequence[SeenElement]:
        if not self.present(image):
            return ()
        return (SeenElement(self.element, None, pixel_box(image, self.region)),)


@dataclass(frozen=True)
class ContentDetector:
    element: ModelElement
    region: Region
    read: Callable[[np.ndarray], str | None]

    def detect(self, image: np.ndarray) -> Sequence[SeenElement]:
        content = self.read(image)
        if content is None:
            return ()
        return (SeenElement(self.element, content, pixel_box(image, self.region)),)


@dataclass(frozen=True)
class UnitListDetector:
    def detect(self, image: np.ndarray) -> Sequence[SeenElement]:
        state = unit_list(image)
        if state is UnitListButton.ABSENT:
            return ()
        box = pixel_box(image, UNIT_LIST_BOXES[state])
        return (SeenElement(ModelElement.UNIT_LIST_BUTTON, state.value, box),)


def _title(image: np.ndarray) -> str | None:
    title = top_left_title(image)
    return None if title is None else title.value


def _phase(image: np.ndarray) -> str | None:
    read = phase(image)
    return None if read is None else read.value


def _round(image: np.ndarray) -> str | None:
    kind = round_button(image)
    return None if kind is None else kind.value


def _unit_detail_shape(name: str) -> Callable[[np.ndarray], bool]:
    return lambda image: has_unit_detail_shape(image, name)


UNIT_DETAIL_PARTS: dict[str, ModelElement] = {
    "detail_button": ModelElement.UNIT_DETAIL_DETAIL_BUTTON,
    "close_button": ModelElement.UNIT_DETAIL_CLOSE_BUTTON,
    "mech_panel": ModelElement.UNIT_DETAIL_MECH_PANEL,
    "pilot_panel": ModelElement.UNIT_DETAIL_PILOT_PANEL,
    "box_weapons": ModelElement.UNIT_DETAIL_BOX_WEAPONS,
    "box_abilities": ModelElement.UNIT_DETAIL_BOX_ABILITIES,
    "box_parts": ModelElement.UNIT_DETAIL_BOX_PARTS,
    "box_pilot_skills": ModelElement.UNIT_DETAIL_BOX_PILOT_SKILLS,
    "box_pilot_abilities": ModelElement.UNIT_DETAIL_BOX_PILOT_ABILITIES,
}

DETECTORS: tuple[ElementDetector, ...] = (
    ShapeDetector(ModelElement.TURN_BOX, TURN_BOX_REGION, has_turn_box),
    ContentDetector(ModelElement.TOP_LEFT_TITLE, TITLE_REGION, _title),
    ContentDetector(ModelElement.TITLE_BAND, TITLE_BAND_REGION, _phase),
    ContentDetector(ModelElement.ROUND_BUTTON, ROUND_BOX, _round),
    ShapeDetector(ModelElement.FAST_FORWARD, FAST_FORWARD_BOX, has_fast_forward),
    ShapeDetector(ModelElement.TAP_TO_NEXT, TAP_TO_NEXT_REGION, has_tap_to_next),
    ContentDetector(ModelElement.AUTO_KEY, AUTO_RECT, lambda image: auto_mode(image).value),
    UnitListDetector(),
    ShapeDetector(ModelElement.UNIT_DETAIL_TITLE, UNIT_DETAIL_TITLE_REGION, has_unit_detail_title),
    *(
        ShapeDetector(element, {**BUTTON_REGIONS, **BLOCK_REGIONS}[name], _unit_detail_shape(name))
        for name, element in UNIT_DETAIL_PARTS.items()
    ),
)
