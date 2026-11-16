from __future__ import annotations

import numpy as np

from ggge_ai_2.interpreter.elements.region import locate
from ggge_ai_2.screenmodel.contract import Rect

# The list button sits left of the pilot circles, so its place depends on the number of pilots.
LIST_SEARCH: Rect = (424, 882, 776, 964)
LIST_SCORE = 0.7
# The pilot circles center on this x, so the row reaches as far right of the center as the
# list button reaches left of it.
ROW_CENTER = 965
ROW_TOP, ROW_BOTTOM = 830, 1080
ROW_MARGIN = 10


def pilot_row(image: np.ndarray) -> tuple[Rect, ...]:
    """Return the box of the pilot row of the battle prep screens, from the list button."""
    score, (x, _) = locate(image, LIST_SEARCH, "prep_list")
    if score < LIST_SCORE:
        return ()
    left = x - ROW_MARGIN
    return ((left, ROW_TOP, 2 * ROW_CENTER - left, ROW_BOTTOM),)
