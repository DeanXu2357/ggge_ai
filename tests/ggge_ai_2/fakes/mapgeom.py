from __future__ import annotations

import math
from dataclasses import dataclass

from ggge_ai_2.display import Size
from ggge_ai_2.mapgeom.contract import CellVector, ViewCell, WorldCell
from ggge_ai_2.stream.contract import FramePoint, FrameVector


@dataclass(frozen=True)
class GridProjection:
    frame_seq: int
    shift: WorldCell
    cell: float = 100.0
    frame: Size = Size(2340, 1080)

    def to_view(self, point: FramePoint) -> ViewCell | None:
        if not (0 <= point.x < self.frame.width and 0 <= point.y < self.frame.height):
            return None
        return (math.floor(point.x / self.cell), math.floor(point.y / self.cell))

    def to_frame(self, cell: WorldCell) -> FramePoint | None:
        point = self._center(cell)
        return point if self.to_view(point) is not None else None

    def to_world(self, cell: ViewCell) -> WorldCell:
        return (cell[0] + self.shift[0], cell[1] + self.shift[1])

    def camera_move(self, displacement: FrameVector, at: FramePoint) -> CellVector:
        return CellVector(-displacement.dx / self.cell, -displacement.dy / self.cell)

    def pan_for(self, cell: WorldCell, to: FramePoint) -> FrameVector:
        now = self._center(cell)
        return FrameVector(to.x - now.x, to.y - now.y)

    def _center(self, cell: WorldCell) -> FramePoint:
        view_x, view_y = cell[0] - self.shift[0], cell[1] - self.shift[1]
        return FramePoint((view_x + 0.5) * self.cell, (view_y + 0.5) * self.cell)
