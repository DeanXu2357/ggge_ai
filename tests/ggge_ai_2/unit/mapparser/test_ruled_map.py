import pytest

from ggge_ai_2.mapparser.opencv_parser import OpenCvMapParser
from ggge_ai_2.stream.contract import Frame
from tests.ggge_ai_2.dataset import Case, cases, load_image

PARSER = OpenCvMapParser()
MAP_CASES = [case for case in cases() if case.map is not None]


def _frame(case: Case) -> Frame:
    return Frame(load_image(case), 0.0, 0)


@pytest.mark.parametrize("case", MAP_CASES, ids=[case.id for case in MAP_CASES])
def test_reads_the_cells_that_the_user_ruled(case: Case) -> None:
    reading = PARSER.parse(_frame(case))
    label = case.map

    assert reading is not None and label is not None
    assert set(reading.cells) == label.cells


@pytest.mark.parametrize("case", MAP_CASES, ids=[case.id for case in MAP_CASES])
def test_reads_the_map_edges_that_the_user_ruled(case: Case) -> None:
    reading = PARSER.parse(_frame(case))
    label = case.map

    assert reading is not None and label is not None
    assert {edge.value for edge in reading.borders} == label.borders


@pytest.mark.parametrize("case", MAP_CASES, ids=[case.id for case in MAP_CASES])
def test_reads_the_unit_cells_that_the_user_ruled(case: Case) -> None:
    reading = PARSER.parse(_frame(case))
    label = case.map

    assert reading is not None and label is not None
    assert {(unit.pos, unit.size) for unit in reading.units} == label.units


@pytest.mark.parametrize("case", MAP_CASES, ids=[case.id for case in MAP_CASES])
def test_reads_the_controllable_units_that_the_user_ruled(case: Case) -> None:
    reading = PARSER.parse(_frame(case))
    label = case.map

    assert reading is not None and label is not None
    assert {unit.pos for unit in reading.units if unit.controllable} == label.controllable


@pytest.mark.parametrize("case", MAP_CASES, ids=[case.id for case in MAP_CASES])
def test_locates_exactly_the_cells_that_the_user_ruled(case: Case) -> None:
    frame = _frame(case)
    label = case.map
    assert label is not None
    right = max(column for column, _ in label.cells) + 1
    bottom = max(row for _, row in label.cells) + 1
    box = {(column, row) for column in range(-1, right + 1) for row in range(-1, bottom + 1)}

    located = {cell for cell in box if PARSER.locate(frame, cell) is not None}

    assert located == label.cells
