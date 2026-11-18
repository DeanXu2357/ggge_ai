import numpy as np
import pytest

from ggge_ai_2.mapparser.border import read_border
from ggge_ai_2.mapparser.contract import ViewCell
from ggge_ai_2.mapparser.lattice import read_lattice
from ggge_ai_2.mapparser.opencv_parser import OpenCvMapParser
from ggge_ai_2.mapparser.region import read_region
from ggge_ai_2.mapparser.topview import top_view
from ggge_ai_2.stream.contract import Frame
from tests.ggge_ai_2.unit.mapparser.scope import scope_of
from tests.ggge_ai_2.dataset import Case, cases, load_image

PARSER = OpenCvMapParser()
RULED = [case for case in cases() if case.tap_mark_ruled]


def _ruled_cell(case: Case, image: np.ndarray, point: tuple[int, int]) -> ViewCell | None:
    lattice = read_lattice(image)
    assert lattice is not None
    rects = scope_of(case).occluded
    region = read_region(lattice, rects, read_border(top_view(image, lattice, rects)))
    cell = lattice.cell_at(point)
    return region.to_view(cell) if cell is not None and region.holds(cell) else None


@pytest.mark.parametrize("case", RULED, ids=[case.id for case in RULED])
def test_reads_the_tap_mark_that_the_user_ruled(case: Case) -> None:
    image = load_image(case)
    reading = PARSER.parse(Frame(image, 0.0, 0), scope_of(case))
    label = case.tap_mark
    cell = None if label is None else _ruled_cell(case, image, label.point)

    assert reading is not None
    if cell is None:
        assert reading.tap_mark is None
        return
    assert reading.tap_mark is not None and label is not None
    assert reading.tap_mark.cell == cell
    terrain = reading.tap_mark.terrain
    assert (None if terrain is None else tuple(item.value for item in terrain)) == label.terrain
