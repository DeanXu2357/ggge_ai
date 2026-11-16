from __future__ import annotations

from collections.abc import Iterable, Sequence

import numpy as np

from ggge_ai_2.mapgeom.contract import (
    CellContent,
    CellSeen,
    Faction,
    MapCell,
    NameMask,
    Side,
    TapMark,
    UnitBrief,
    UnitRole,
    View,
    ViewCell,
    ViewUnit,
)
from ggge_ai_2.mapgeom.stitch import StitchMapGeometry

BIG = (
    ".#.#..#.#.##..#.....",
    ".#..##..#....###....",
    "...........#..#.#...",
    "..........#.......#.",
    "###.#...#..........#",
    "#.....#........#....",
    "..#.####.####.#..#..",
    ".#....##...##..#.#..",
    "....#..............#",
    "#...........##......",
)

SPARSE = (
    "....................",
    "..#.................",
    "..........#.........",
    "....................",
    ".................#..",
    "....................",
)

DIAGONAL = (
    "..............",
    "..#...........",
    "..............",
    ".....#........",
    "..............",
    "........#.....",
    "..............",
    "..............",
)

EVEN_ROW = (
    "..#.....#.....#....",
    "...................",
)


def occupancy(rows: Sequence[str]) -> dict[MapCell, CellContent]:
    return {
        (x, y): CellContent.OCCUPIED if mark == "#" else CellContent.EMPTY
        for y, row in enumerate(rows)
        for x, mark in enumerate(row)
    }


def cut(
    rows: Sequence[str],
    left: int,
    top: int,
    width: int,
    height: int,
    *,
    unreadable: Iterable[ViewCell] = (),
    flipped: Iterable[ViewCell] = (),
    units: tuple[ViewUnit, ...] = (),
    tap_mark: TapMark | None = None,
) -> View:
    hidden, swapped = set(unreadable), set(flipped)
    cells: dict[ViewCell, CellSeen] = {}
    for y in range(height):
        for x in range(width):
            occupied = (rows[top + y][left + x] == "#") != ((x, y) in swapped)
            if (x, y) in hidden:
                cells[(x, y)] = CellSeen.UNREADABLE
            else:
                cells[(x, y)] = CellSeen.OCCUPIED if occupied else CellSeen.EMPTY
    borders = {
        side
        for side, seen in (
            (Side.LEFT, left == 0),
            (Side.TOP, top == 0),
            (Side.RIGHT, left + width == len(rows[0])),
            (Side.BOTTOM, top + height == len(rows)),
        )
        if seen
    }
    return View(None, None, None, cells, frozenset(borders), units, tap_mark)


def brief(seed: int) -> UnitBrief:
    rng = np.random.default_rng(seed)
    mech = (rng.random((20, 60)) < 0.4).astype(np.uint8) * 255
    pilot = (rng.random((20, 60)) < 0.4).astype(np.uint8) * 255
    return UnitBrief(
        UnitRole.ATTACK, NameMask(mech), 1200, 150, UnitRole.SUPPORT, NameMask(pilot), 10, 20, None
    )


def quadrants() -> list[View]:
    return [cut(BIG, left, top, 12, 6) for left, top in ((0, 0), (8, 0), (0, 4), (8, 4))]


def test_one_view_is_the_judgment():
    judgment = StitchMapGeometry().judge([cut(BIG, 0, 0, 12, 6)])

    assert judgment is not None
    assert judgment.cells == {
        cell: content for cell, content in occupancy(BIG).items() if cell[0] < 12 and cell[1] < 6
    }
    assert (judgment.columns.size(), judgment.rows.size()) == (None, None)
    assert judgment.columns.start_closed and judgment.rows.start_closed


def test_shape_joins_four_corners_into_the_whole_map():
    judgment = StitchMapGeometry().judge(quadrants())

    assert judgment is not None
    assert judgment.cells == occupancy(BIG)
    assert judgment.uncertain == frozenset()
    assert (judgment.columns.size(), judgment.rows.size()) == (20, 10)
    assert judgment.current == frozenset((x, y) for x in range(8, 20) for y in range(4, 10))


def test_shape_joins_views_in_any_order():
    views = quadrants()
    judgment = StitchMapGeometry().judge([views[3], views[0], views[2], views[1]])

    assert judgment is not None
    assert judgment.cells == occupancy(BIG)


def test_shape_cannot_join_sparse_views():
    views = [cut(SPARSE, 0, 0, 12, 6), cut(SPARSE, 8, 0, 12, 6)]

    judgment = StitchMapGeometry().judge(views)

    assert judgment is not None
    assert judgment.columns.length == 12
    assert judgment.current is None


def test_the_shape_with_the_most_matching_units_joins_an_evenly_spaced_pattern():
    view = cut(DIAGONAL, 1, 1, 12, 6)

    judgment = StitchMapGeometry().judge([view, view])

    assert judgment is not None
    assert judgment.current == frozenset((x, y) for x in range(12) for y in range(6))


def test_two_shapes_with_the_same_evidence_do_not_join():
    views = [cut(EVEN_ROW, 1, 0, 17, 2), cut(EVEN_ROW, 2, 0, 7, 2)]

    judgment = StitchMapGeometry().judge(views)

    assert judgment is not None
    assert judgment.current is None


def test_borders_on_both_axes_join_sparse_views():
    views = [cut(SPARSE, 0, 0, 12, 6), cut(SPARSE, 0, 0, 9, 6)]

    judgment = StitchMapGeometry().judge(views)

    assert judgment is not None
    assert judgment.current == frozenset((x, y) for x in range(9) for y in range(6))


def test_a_border_on_one_axis_breaks_a_tie_of_two_shapes():
    rows = ("." * 19, *EVEN_ROW, "." * 19)
    views = [cut(rows, 0, 1, 17, 2), cut(rows, 0, 1, 9, 2)]

    judgment = StitchMapGeometry().judge(views)

    assert judgment is not None
    assert judgment.current == frozenset((x, y) for x in range(9) for y in range(2))


def test_units_with_the_same_brief_do_not_join_sparse_views():
    # Generic enemies share the mech, the pilot and every value of the brief.
    same = brief(1)
    views = [
        cut(SPARSE, 0, 0, 12, 6, units=(ViewUnit((10, 2), (1, 1), None, Faction.ENEMY, same),)),
        cut(SPARSE, 8, 0, 12, 6, units=(ViewUnit((2, 2), (1, 1), None, Faction.ENEMY, same),)),
    ]

    judgment = StitchMapGeometry().judge(views)

    assert judgment is not None
    assert judgment.current is None


def test_a_shared_tap_mark_joins_sparse_views():
    views = [
        cut(SPARSE, 0, 0, 12, 6, tap_mark=TapMark((9, 4), 1)),
        cut(SPARSE, 8, 0, 12, 6, tap_mark=TapMark((1, 4), 1)),
    ]

    judgment = StitchMapGeometry().judge(views)

    assert judgment is not None
    assert judgment.cells == occupancy(SPARSE)


def test_marks_of_two_taps_do_not_join_sparse_views():
    views = [
        cut(SPARSE, 0, 0, 12, 6, tap_mark=TapMark((9, 4), 1)),
        cut(SPARSE, 8, 0, 12, 6, tap_mark=TapMark((1, 4), 2)),
    ]

    judgment = StitchMapGeometry().judge(views)

    assert judgment is not None
    assert judgment.current is None


def test_an_unjoined_last_view_keeps_the_earlier_result():
    empty = ("." * 20,) * 10
    views = [*quadrants(), cut(empty, 4, 2, 12, 6)]

    judgment = StitchMapGeometry().judge(views)

    assert judgment is not None
    assert judgment.cells == occupancy(BIG)
    assert judgment.current is None


def test_two_against_one_settles_a_cell():
    views = [*quadrants(), cut(BIG, 0, 0, 12, 6, flipped=[(5, 5)])]

    judgment = StitchMapGeometry().judge(views)

    assert judgment is not None
    assert judgment.cells == occupancy(BIG)


def test_one_against_one_leaves_a_cell_uncertain():
    views = [cut(BIG, 0, 0, 12, 6), cut(BIG, 0, 0, 12, 6, flipped=[(5, 5)])]

    judgment = StitchMapGeometry().judge(views)

    assert judgment is not None
    assert (5, 5) in judgment.uncertain
    assert (5, 5) not in judgment.cells


def test_an_unreadable_cell_stays_uncertain_until_another_view_reads_it():
    hud = [(x, 5) for x in range(4)]
    alone = StitchMapGeometry().judge([cut(BIG, 0, 0, 12, 6, unreadable=hud)])
    joined = StitchMapGeometry().judge(
        [cut(BIG, 0, 0, 12, 6, unreadable=hud), cut(BIG, 0, 4, 12, 6)]
    )

    assert alone is not None and joined is not None
    assert set(hud) <= alone.uncertain
    assert joined.cells == {
        cell: content for cell, content in occupancy(BIG).items() if cell[0] < 12
    }
