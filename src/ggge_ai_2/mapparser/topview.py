from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from ggge_ai_2.mapparser.contract import ViewCell
from ggge_ai_2.mapparser.hud import Rect, outside
from ggge_ai_2.mapparser.lattice import Lattice

# The top view has CELL x CELL pixels in each cell at every zoom level.
CELL = 96


@dataclass(frozen=True)
class TopView:
    """The frame warped onto the map plane, one square of CELL pixels for each cell.

    The view holds the frame cells and one more cell on each side.
    """

    image: np.ndarray
    white: np.ndarray
    # False where the pixel is outside the frame or under the HUD.
    visible: np.ndarray
    first_column: int
    first_row: int

    @property
    def columns(self) -> int:
        return self.image.shape[1] // CELL

    @property
    def rows(self) -> int:
        return self.image.shape[0] // CELL

    def origin(self, cell: ViewCell) -> tuple[int, int]:
        """Return the (x, y) pixel of the top left corner of the cell."""
        return (cell[0] - self.first_column) * CELL, (cell[1] - self.first_row) * CELL

    def cell(self, cell: ViewCell) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return the image, the white channel and the visibility of the cell."""
        left, top = self.origin(cell)
        window = (slice(top, top + CELL), slice(left, left + CELL))
        return self.image[window], self.white[window], self.visible[window]


def top_view(image: np.ndarray, lattice: Lattice, rects: tuple[Rect, ...]) -> TopView:
    cells = lattice.cells()
    first_column = min(column for column, _ in cells) - 1
    first_row = min(row for _, row in cells) - 1
    columns = max(column for column, _ in cells) - first_column + 2
    rows = max(row for _, row in cells) - first_row + 2
    # The lattice maps (column, row) to the frame with one homography.
    cs, co = lattice.column_step, lattice.column_origin
    rs, ro = lattice.row_step, lattice.row_origin
    to_frame = np.array(
        [
            [cs, lattice.apex * rs, lattice.apex * ro + co],
            [0.0, lattice.horizon * rs, lattice.horizon * ro + 1.0],
            [0.0, rs, ro],
        ]
    )
    to_cells = np.array(
        [[1.0 / CELL, 0.0, first_column], [0.0, 1.0 / CELL, first_row], [0.0, 0.0, 1.0]]
    )
    size = (columns * CELL, rows * CELL)
    inverse = cv2.WARP_INVERSE_MAP
    view = cv2.warpPerspective(image, to_frame @ to_cells, size, flags=cv2.INTER_LINEAR | inverse)
    mask = outside(image, rects, 0).astype(np.uint8)
    shown = cv2.warpPerspective(mask, to_frame @ to_cells, size, flags=cv2.INTER_NEAREST | inverse)
    white = view.min(axis=2).astype(np.float32)
    return TopView(view, white, shown > 0, first_column, first_row)
