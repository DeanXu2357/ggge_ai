from __future__ import annotations

from ggge_ai_2.mapgeom.contract import Alignment, CellContent, CellHolds, LocalBoard

ALIGNMENT = Alignment((10, 5))
BOARD = LocalBoard(
    {
        (2, 2): CellContent.EMPTY,
        (3, 2): CellContent.OCCUPIED,
        (4, 2): CellContent.UNREADABLE,
    },
    frozenset(),
)


def test_alignment_takes_a_world_cell_to_its_view_cell():
    assert ALIGNMENT.to_view((12, 7)) == (2, 2)


def test_cell_on_the_board_is_compared_with_the_expected_content():
    assert CellHolds((12, 7), CellContent.EMPTY).holds_on(BOARD, ALIGNMENT)
    assert not CellHolds((13, 7), CellContent.EMPTY).holds_on(BOARD, ALIGNMENT)


def test_cell_outside_the_board_does_not_hold():
    assert not CellHolds((99, 99), CellContent.EMPTY).holds_on(BOARD, ALIGNMENT)


def test_unreadable_cell_does_not_hold_the_expected_content():
    assert not CellHolds((14, 7), CellContent.EMPTY).holds_on(BOARD, ALIGNMENT)
