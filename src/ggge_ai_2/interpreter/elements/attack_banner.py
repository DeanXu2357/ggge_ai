from __future__ import annotations

import cv2
import numpy as np

from ggge_ai_2.screenmodel.contract import Rect

# The banner between the two unit panels has two bars: the strike above the response. A bar
# is red or blue by its faction, so the cue is the saturation edge at the top and at the
# bottom of each bar, in the middle columns of the bars.
BAR_COLUMNS = (1040, 1320)
# (first row, last row, sign): the saturation rises at the top of a bar and falls at its
# bottom.
BAR_EDGES = ((105, 117, 1), (147, 160, -1), (216, 228, 1), (257, 276, -1))
BAR_EDGE_STEP = 8.5
BANNER_BOX: Rect = (975, 50, 1385, 295)


def attack_banner(image: np.ndarray) -> tuple[Rect, ...]:
    left, right = BAR_COLUMNS
    saturation = cv2.cvtColor(image[: BANNER_BOX[3], left:right], cv2.COLOR_BGR2HSV)[..., 1]
    profile = np.diff(saturation.astype(np.float32), axis=0).mean(axis=1)
    if any(
        float((sign * profile[first:last]).max()) < BAR_EDGE_STEP for first, last, sign in BAR_EDGES
    ):
        return ()
    return (BANNER_BOX,)
