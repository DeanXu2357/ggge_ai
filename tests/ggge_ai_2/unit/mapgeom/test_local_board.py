import pytest

from ggge_ai_2.mapgeom.contract import CellContent, CellHolds, LocalBoard
from ggge_ai_2.verdict import Verdict

EXTENT = frozenset({(3, 4), (4, 4)})


def board(cells) -> LocalBoard:
    return LocalBoard(projection=object(), extent=EXTENT, cells=cells)


def test_board_refuses_a_cell_outside_its_extent():
    with pytest.raises(ValueError):
        board({(9, 9): CellContent.EMPTY})


def test_cell_outside_the_extent_is_unreadable_not_empty():
    seen = board({(3, 4): CellContent.EMPTY})

    assert CellHolds((9, 9), CellContent.EMPTY).holds_on(seen) is Verdict.UNREADABLE


def test_cell_inside_the_extent_is_compared():
    seen = board({(3, 4): CellContent.EMPTY, (4, 4): CellContent.OCCUPIED})

    assert CellHolds((3, 4), CellContent.EMPTY).holds_on(seen) is Verdict.HOLDS
    assert CellHolds((4, 4), CellContent.EMPTY).holds_on(seen) is Verdict.DOES_NOT_HOLD
