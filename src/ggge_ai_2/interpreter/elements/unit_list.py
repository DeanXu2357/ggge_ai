from __future__ import annotations

from enum import StrEnum

import numpy as np

from ggge_ai_2.interpreter.elements.region import Region, match


class UnitListButton(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    ABSENT = "absent"


# The button moves down by 235 px (0.2176 of the height) when the card row closes.
UNIT_LIST_LABEL_REGIONS: dict[UnitListButton, Region] = {
    UnitListButton.OPEN: (0.808, 0.689, 0.865, 0.730),
    UnitListButton.CLOSED: (0.808, 0.906, 0.865, 0.947),
}
UNIT_LIST_ARROW_REGIONS: dict[UnitListButton, Region] = {
    UnitListButton.OPEN: (0.783, 0.689, 0.802, 0.730),
    UnitListButton.CLOSED: (0.783, 0.906, 0.802, 0.947),
}
UNIT_LIST_MARGIN = 12
UNIT_LIST_LABEL_SCORE = 0.7
UNIT_LIST_ARROW_SCORE = 0.7


def unit_list_scores(image: np.ndarray) -> dict[str, float]:
    scores: dict[str, float] = {}
    for state, region in UNIT_LIST_LABEL_REGIONS.items():
        scores[f"{state}_label"] = match(image, region, "unit_list_label", UNIT_LIST_MARGIN)
        scores[f"{state}_arrow"] = match(
            image, UNIT_LIST_ARROW_REGIONS[state], f"unit_list_arrow_{state}", UNIT_LIST_MARGIN
        )
    return scores


def unit_list(image: np.ndarray) -> UnitListButton:
    scores = unit_list_scores(image)
    for state in UNIT_LIST_LABEL_REGIONS:
        if (
            scores[f"{state}_label"] >= UNIT_LIST_LABEL_SCORE
            and scores[f"{state}_arrow"] >= UNIT_LIST_ARROW_SCORE
        ):
            return state
    return UnitListButton.ABSENT
