import functools

import pytest

from ggge_ai_2.mapparser.contract import CellReading, UnitReading, ViewCell
from ggge_ai_2.mapparser.lattice import read_lattice
from ggge_ai_2.mapparser.topview import top_view
from ggge_ai_2.mapparser.units import covered, read_units
from tests.ggge_ai_2.dataset import Case, cases, load_image
from tests.ggge_ai_2.unit.mapparser.scope import scope_of
from tests.ggge_ai_2.unit.mapparser.test_lattice import GRID_CASES, NO_GRID_CASES


def _read(case: Case) -> tuple[tuple[UnitReading, ...], dict[ViewCell, CellReading]] | None:
    return _read_id(case.id)


@functools.cache
def _read_id(case_id: str) -> tuple[tuple[UnitReading, ...], dict[ViewCell, CellReading]] | None:
    case = next(case for case in cases() if case.id == case_id)
    image = load_image(case)
    lattice = read_lattice(image)
    if lattice is None:
        return None
    scope = scope_of(case)
    view = top_view(image, lattice, scope.occluded)
    return read_units(image, lattice, scope.occluded, view, scope.chevrons)


def _units(case: Case) -> tuple[UnitReading, ...]:
    reading = _read(case)
    assert reading is not None
    return reading[0]


def _footprint(unit: UnitReading) -> set[ViewCell]:
    column, row = unit.pos
    width, height = unit.size
    return {(column + dx, row + dy) for dx in range(width) for dy in range(height)}


@pytest.mark.parametrize("case", NO_GRID_CASES, ids=[case.id for case in NO_GRID_CASES])
def test_reads_no_unit_where_the_frame_shows_no_grid(case: Case) -> None:
    reading = _read(case)

    assert reading is None or reading[0] == ()


@pytest.mark.parametrize("case", GRID_CASES, ids=[case.id for case in GRID_CASES])
def test_reads_every_frame_cell(case: Case) -> None:
    image = load_image(case)
    lattice = read_lattice(image)
    assert lattice is not None
    rects = scope_of(case).occluded

    reading = _read(case)

    assert reading is not None
    _, cells = reading
    assert set(cells) == set(lattice.cells())
    assert all(
        cells[cell] is CellReading.UNREADABLE
        for cell in lattice.cells()
        if covered(lattice.center(cell), rects)
    )


@pytest.mark.parametrize("case", GRID_CASES, ids=[case.id for case in GRID_CASES])
def test_footprints_do_not_overlap(case: Case) -> None:
    footprints = [_footprint(unit) for unit in _units(case)]

    assert sum(len(footprint) for footprint in footprints) == len(set().union(*footprints))


@pytest.mark.parametrize("case", GRID_CASES, ids=[case.id for case in GRID_CASES])
def test_occupied_cells_are_the_readable_footprint_cells(case: Case) -> None:
    reading = _read(case)
    assert reading is not None
    units, cells = reading
    covered = set().union(*(_footprint(unit) for unit in units))

    occupied = {cell for cell, value in cells.items() if value is CellReading.OCCUPIED}
    readable = {cell for cell, value in cells.items() if value is not CellReading.UNREADABLE}

    assert occupied == covered & readable
