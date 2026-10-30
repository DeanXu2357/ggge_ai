import functools

import pytest

from ggge_ai_2.mapparser.contract import Marker, ViewCell
from ggge_ai_2.mapparser.hud import hud_cells, hud_rects
from ggge_ai_2.mapparser.lattice import read_lattice
from ggge_ai_2.mapparser.markers import read_markers
from ggge_ai_2.mapparser.topview import top_view
from tests.ggge_ai_2.dataset import Case, load_image
from tests.ggge_ai_2.unit.mapparser.test_lattice import GRID_CASES

# The game draws the move range after the player selects a unit to move.
MOVE_SCREENS = frozenset({"select_action_in_battle"})
UNIT_SCREENS = MOVE_SCREENS | {
    "select_skill_in_battle",
    "select_weapon_in_battle",
    "select_weapon_in_battle_response",
}
WEAPON_SCREENS = frozenset({"select_weapon_in_battle", "select_weapon_in_battle_response"})

MOVE_CASES = [case for case in GRID_CASES if case.screen in MOVE_SCREENS]
NO_UNIT_CASES = [case for case in GRID_CASES if case.screen not in UNIT_SCREENS]
NO_WEAPON_CASES = [case for case in GRID_CASES if case.screen not in WEAPON_SCREENS]


CASES_BY_ID = {case.id: case for case in GRID_CASES}


def _read(case: Case) -> dict[ViewCell, frozenset[Marker]]:
    return _read_by_id(case.id)


# Keyed by the case ID because a Case holds a dict and does not hash.
@functools.cache
def _read_by_id(case_id: str) -> dict[ViewCell, frozenset[Marker]]:
    image = load_image(CASES_BY_ID[case_id])
    lattice = read_lattice(image)
    assert lattice is not None
    rects = hud_rects(image)
    cells = lattice.cells() - hud_cells(image, lattice)
    return read_markers(image, top_view(image, lattice, rects), cells)


def _marked(case: Case, marker: Marker) -> set[ViewCell]:
    return {cell for cell, found in _read(case).items() if marker in found}


@pytest.mark.parametrize("case", GRID_CASES, ids=[case.id for case in GRID_CASES])
def test_reads_each_given_cell(case: Case) -> None:
    image = load_image(case)
    lattice = read_lattice(image)
    assert lattice is not None

    assert set(_read(case)) == lattice.cells() - hud_cells(image, lattice)


@pytest.mark.parametrize("case", MOVE_CASES, ids=[case.id for case in MOVE_CASES])
def test_reads_a_move_range_on_the_move_screen(case: Case) -> None:
    assert _marked(case, Marker.MOVE_RANGE)


@pytest.mark.parametrize("case", NO_UNIT_CASES, ids=[case.id for case in NO_UNIT_CASES])
def test_reads_no_move_range_and_no_threat_where_no_unit_is_selected(case: Case) -> None:
    assert not _marked(case, Marker.MOVE_RANGE)
    assert not _marked(case, Marker.THREAT)


@pytest.mark.parametrize("case", NO_WEAPON_CASES, ids=[case.id for case in NO_WEAPON_CASES])
def test_reads_no_weapon_range_outside_the_weapon_screens(case: Case) -> None:
    assert not _marked(case, Marker.WEAPON_RANGE)


@pytest.mark.parametrize("case", GRID_CASES, ids=[case.id for case in GRID_CASES])
def test_a_threat_is_inside_the_move_range(case: Case) -> None:
    assert _marked(case, Marker.THREAT) <= _marked(case, Marker.MOVE_RANGE)
