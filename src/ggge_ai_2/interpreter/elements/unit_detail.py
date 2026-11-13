from __future__ import annotations

import numpy as np

from ggge_ai_2.interpreter.elements.region import Region, match
from ggge_ai_2.interpreter.elements.shape import shape_score

BUTTON_REGIONS: dict[str, Region] = {
    "detail_button": (0.7701, 0.0602, 0.8902, 0.1231),
    "close_button": (0.4256, 0.8444, 0.5833, 0.9852),
}
TITLE_REGION: Region = (0.4444, 0.0611, 0.5684, 0.113)
BLOCK_REGIONS: dict[str, Region] = {
    "mech_panel": (0.1303, 0.1204, 0.5718, 0.5741),
    "pilot_panel": (0.5782, 0.1204, 0.8769, 0.5741),
    "box_weapons": (0.1338, 0.7037, 0.3303, 0.8278),
    "box_abilities": (0.3316, 0.7037, 0.4611, 0.8278),
    "box_parts": (0.462, 0.7037, 0.5697, 0.8278),
    "box_pilot_skills": (0.5808, 0.7037, 0.7432, 0.8278),
    "box_pilot_abilities": (0.7444, 0.7037, 0.8752, 0.8278),
}
SHAPE_MARGIN = 8
SHAPE_SCORE = 0.85
TITLE_MARGIN = 8
TITLE_SCORE = 0.8


def has_unit_detail_shape(image: np.ndarray, name: str) -> bool:
    region = {**BUTTON_REGIONS, **BLOCK_REGIONS}[name]
    return shape_score(image, region, f"unit_detail_{name}", SHAPE_MARGIN) >= SHAPE_SCORE


def has_unit_detail_title(image: np.ndarray) -> bool:
    return match(image, TITLE_REGION, "unit_detail_title", TITLE_MARGIN) >= TITLE_SCORE
