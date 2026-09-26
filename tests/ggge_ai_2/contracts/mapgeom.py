import pytest

from ggge_ai_2.mapgeom.contract import CellVector, Projection, WorldCell

CELL_TOLERANCE = 0.5


class ProjectionContract:
    """Subclass per implementation with a fitted projection and cells that it shows."""

    def make(self) -> Projection:
        raise NotImplementedError

    def visible_cells(self) -> list[WorldCell]:
        raise NotImplementedError

    def test_cell_to_frame_and_back_is_the_same_cell(self):
        projection = self.make()
        for cell in self.visible_cells():
            point = projection.to_frame(cell)

            assert point is not None
            assert projection.to_world(projection.to_view(point)) == cell

    def test_camera_move_undoes_the_pan_toward_a_cell(self):
        projection = self.make()
        target, anchor = self.visible_cells()[0], self.visible_cells()[-1]
        to = projection.to_frame(anchor)

        move = projection.camera_move(projection.pan_for(target, to), to)

        expected = CellVector(target[0] - anchor[0], target[1] - anchor[1])
        assert move.dx == pytest.approx(expected.dx, abs=CELL_TOLERANCE)
        assert move.dy == pytest.approx(expected.dy, abs=CELL_TOLERANCE)
