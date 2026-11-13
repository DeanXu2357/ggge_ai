from __future__ import annotations

import numpy as np

from ggge_ai_2.interpreter.elements.shape import VERTICAL, direction_edges, edge_near
from ggge_ai_2.screenmodel.contract import Rect

# The panel is translucent, so its top, right and bottom edges fade where the map behind it
# has the same brightness (map20261026-40, rec20261014-871). Its left side is a thin white
# line that shows on every map.
PANEL_LINE_X = 1542
PANEL_LINE_ROWS = (296, 524)
PANEL_LINE_MARGIN = 10
PANEL_LINE_SHARE = 0.95
PANEL_BOX: Rect = (1538, 280, 2216, 545)


def description_panel(image: np.ndarray) -> tuple[Rect, ...]:
    top, bottom = PANEL_LINE_ROWS
    margin = PANEL_LINE_MARGIN
    labels = direction_edges(
        image[top - margin : bottom + margin, PANEL_LINE_X - margin : PANEL_LINE_X + margin]
    )
    if float(edge_near(labels, VERTICAL)[margin:-margin, margin].mean()) < PANEL_LINE_SHARE:
        return ()
    return (PANEL_BOX,)
