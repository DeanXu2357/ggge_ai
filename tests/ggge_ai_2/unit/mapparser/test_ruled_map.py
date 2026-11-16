"""Strict layer: the parser reads these exactly as the user ruled them."""

import pytest

from ggge_ai_2.mapparser.opencv_parser import OpenCvMapParser
from ggge_ai_2.stream.contract import Frame
from tests.ggge_ai_2.unit.mapparser.scope import scope_of
from tests.ggge_ai_2.dataset import Case, cases, load_image

PARSER = OpenCvMapParser()
MAP_CASES = [case for case in cases() if case.map is not None]


def _frame(case: Case) -> Frame:
    return Frame(load_image(case), 0.0, 0)


@pytest.mark.parametrize("case", MAP_CASES, ids=[case.id for case in MAP_CASES])
def test_reads_the_cells_that_the_user_ruled(case: Case) -> None:
    reading = PARSER.parse(_frame(case), scope_of(case))
    label = case.map

    assert reading is not None and label is not None
    assert set(reading.cells) == label.cells


@pytest.mark.parametrize("case", MAP_CASES, ids=[case.id for case in MAP_CASES])
def test_reads_the_map_edges_that_the_user_ruled(case: Case) -> None:
    reading = PARSER.parse(_frame(case), scope_of(case))
    label = case.map

    assert reading is not None and label is not None
    assert {edge.value for edge in reading.borders} == label.borders


@pytest.mark.parametrize("case", MAP_CASES, ids=[case.id for case in MAP_CASES])
def test_reads_the_controllable_units_that_the_user_ruled(case: Case) -> None:
    reading = PARSER.parse(_frame(case), scope_of(case))
    label = case.map

    assert reading is not None and label is not None
    assert {
        unit.pos for unit in reading.units if unit.controllable and not unit.cropped
    } == label.controllable


@pytest.mark.parametrize("case", MAP_CASES, ids=[case.id for case in MAP_CASES])
def test_reads_the_selected_unit_that_the_user_ruled(case: Case) -> None:
    reading = PARSER.parse(_frame(case), scope_of(case))
    label = case.map

    assert reading is not None and label is not None
    selected = {unit.pos for unit in reading.units if unit.selected and not unit.cropped}
    assert selected == ({label.selected} if label.selected is not None else set())


@pytest.mark.parametrize("case", MAP_CASES, ids=[case.id for case in MAP_CASES])
def test_reads_the_selected_enemy_that_the_user_ruled(case: Case) -> None:
    reading = PARSER.parse(_frame(case), scope_of(case))
    label = case.map

    assert reading is not None and label is not None
    selected = {unit.pos for unit in reading.units if unit.enemy_selected and not unit.cropped}
    assert selected == ({label.enemy_selected} if label.enemy_selected is not None else set())


@pytest.mark.parametrize("case", MAP_CASES, ids=[case.id for case in MAP_CASES])
def test_places_exactly_the_cells_that_the_user_ruled(case: Case) -> None:
    reading = PARSER.parse(_frame(case), scope_of(case))
    label = case.map

    assert reading is not None and label is not None
    assert set(reading.places) == label.cells


CROPPED_CASES = [
    case for case in MAP_CASES if case.map is not None and case.map.cropped is not None
]


@pytest.mark.parametrize("case", CROPPED_CASES, ids=[case.id for case in CROPPED_CASES])
def test_reads_the_cut_units_that_the_user_ruled(case: Case) -> None:
    reading = PARSER.parse(_frame(case), scope_of(case))
    label = case.map

    assert reading is not None and label is not None
    read = {
        (unit.pos, unit.size)
        for unit in reading.units
        if unit.cropped
        and any(
            (unit.pos[0] + dx, unit.pos[1] + dy) in reading.cells
            for dx in range(unit.size[0])
            for dy in range(unit.size[1])
        )
    }
    assert read == label.cropped
