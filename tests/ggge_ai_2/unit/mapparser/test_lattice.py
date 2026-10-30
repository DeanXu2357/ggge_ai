import pytest

from ggge_ai_2.mapparser.lattice import Lattice, read_lattice
from tests.ggge_ai_2.dataset import Case, cases, load_image

GRID_SCREENS = frozenset(
    {
        "player_phase_overview",
        "select_action_in_battle",
        "select_skill_in_battle",
        "select_weapon_in_battle",
        "select_weapon_in_battle_response",
        "battle_prep_attack",
        "battle_prep_response_attack",
        "non_player_phase_battle_view",
    }
)
# The attack animation zooms the camera. Some of its frames show the grid and some do not.
UNSETTLED_SCREENS = frozenset({"simplify_weapon_anime"})
# These frames show no grid lines: the second stage of the recording and run 20261024-183527.
GRID_OFF_CASES = frozenset(
    {"rec20261014-1585", "rec20261014-1645", "rec20261014-1691", "run20261024-183527-15"}
)

GRID_CASES = [
    case for case in cases() if case.screen in GRID_SCREENS and case.id not in GRID_OFF_CASES
]
NO_GRID_CASES = [
    case
    for case in cases()
    if case.screen not in GRID_SCREENS | UNSETTLED_SCREENS or case.id in GRID_OFF_CASES
]


def _lattice(case: Case) -> Lattice:
    lattice = read_lattice(load_image(case))
    assert lattice is not None
    return lattice


@pytest.mark.parametrize("case", GRID_CASES, ids=[case.id for case in GRID_CASES])
def test_reads_a_lattice_where_the_frame_shows_the_grid(case: Case) -> None:
    assert read_lattice(load_image(case)) is not None


@pytest.mark.parametrize("case", NO_GRID_CASES, ids=[case.id for case in NO_GRID_CASES])
def test_reads_no_lattice_where_the_frame_shows_no_grid(case: Case) -> None:
    assert read_lattice(load_image(case)) is None


@pytest.mark.parametrize("case", GRID_CASES[:3], ids=[case.id for case in GRID_CASES[:3]])
def test_cells_start_at_column_0_and_row_0(case: Case) -> None:
    cells = _lattice(case).cells()

    assert min(column for column, _ in cells) == 0
    assert min(row for _, row in cells) == 0


@pytest.mark.parametrize("case", GRID_CASES[:3], ids=[case.id for case in GRID_CASES[:3]])
def test_every_cell_has_its_center_in_the_frame(case: Case) -> None:
    lattice = _lattice(case)

    for cell in lattice.cells():
        x, y = lattice.center(cell)
        assert 0 <= x < lattice.width and 0 <= y < lattice.height


@pytest.mark.parametrize("case", GRID_CASES[:3], ids=[case.id for case in GRID_CASES[:3]])
def test_the_cell_at_a_cell_center_is_that_cell(case: Case) -> None:
    lattice = _lattice(case)

    for cell in lattice.cells():
        assert lattice.cell_at(lattice.center(cell)) == cell


@pytest.mark.parametrize("case", GRID_CASES[:3], ids=[case.id for case in GRID_CASES[:3]])
def test_cells_hold_each_neighbor_with_its_center_in_the_frame(case: Case) -> None:
    lattice = _lattice(case)
    cells = lattice.cells()

    for column, row in cells:
        for neighbor in (
            (column - 1, row),
            (column + 1, row),
            (column, row - 1),
            (column, row + 1),
        ):
            assert (neighbor in cells) == lattice.inside(neighbor)
