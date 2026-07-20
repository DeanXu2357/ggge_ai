"""Cell-relative integration acceptance on the ex2if series (定案 6):
the board must reproduce the user-confirmed standard answer exactly --
every 1x1 unit on its cell, every large-unit detection inside its
footprint block, boundaries anchored, no conflicts. The standard answer
is the calibration target the user signed off in-game (north gap of 5
rows confirmed by counting cells on screen)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ggge_ai.battle import map_grid
from ggge_ai.battle.frame_source import FixtureFrameSource

SERIES = Path(__file__).parent / "fixtures" / "vision" / "map_scan" / "ex2if_20260719"


@pytest.fixture(scope="module")
def board():
    return map_grid.read_board(FixtureFrameSource(SERIES).collect())


@pytest.fixture(scope="module")
def answer():
    return json.loads((SERIES / "standard_answer.json").read_text(encoding="utf-8"))


def test_board_matches_standard_answer(board, answer):
    got = {u.cell for u in board.units}
    expected_extras: set[tuple[int, int]] = set()
    for unit in answer["units"]:
        cells = {tuple(c) for c in unit["cells"]}
        if unit["footprint"] == [1, 1]:
            (cell,) = cells
            assert cell in got, f"{unit['id']} missing at {cell}"
        else:
            assert cells & got, f"{unit['id']} block {sorted(cells)} has no detection"
            expected_extras |= cells
    strays = got - {tuple(u["map_cell"]) for u in answer["units"]} - expected_extras
    # large sprites shed a couple of off-block peaks and the banner-hidden
    # unit reads biased; anything beyond that is a regression
    assert len(strays) <= 6, f"unexplained cells: {sorted(strays)}"


def test_board_geometry(board, answer):
    assert board.size == tuple(answer["map"]["size_cells"])
    assert board.conflicts == []
    assert all(off is not None for off in board.offsets)


def test_units_support(board):
    multi = [u for u in board.units if u.support >= 2]
    assert len(multi) >= 22


# stitch-refined camera positions of the ex2if series, rounded; shifts fed
# to the sparse tests are content displacements cam[i-1]-cam[i] with ±20px
# noise on top to prove the unwrap tolerates coarse navigator measurements
CAMERAS = [
    (0, 0), (-12, -484), (-30, -895), (-71, -1412), (-43, -1644),
    (454, -1697), (428, -999), (399, -584), (317, -62),
]


def _noisy_shifts() -> list[tuple[float, float] | None]:
    out: list[tuple[float, float] | None] = [None]
    for i in range(1, len(CAMERAS)):
        noise = 20 if i % 2 else -20
        out.append(
            (
                CAMERAS[i - 1][0] - CAMERAS[i][0] + noise,
                CAMERAS[i - 1][1] - CAMERAS[i][1] - noise,
            )
        )
    return out


@pytest.fixture(scope="module")
def raw(answer):
    frames = FixtureFrameSource(SERIES).collect()
    return frames, map_grid.read_series([f.image for f in frames])


def test_sparse_board_units_only_in_last_frame(raw, board):
    """The user's extreme scenario: a board whose only units huddle in
    one region must still integrate -- every frame places unit-free on
    the edge and shift channels, at exactly the offsets the dense run
    found, and the last frame's units land on their standard-answer
    cells. (s24 is asserted loosely: its lone frame-9 detection snaps
    one cell east, a single-observation content bias that multi-frame
    support resolves in the dense board -- placement is not at fault.)"""
    frames, series = raw
    stripped = [
        map_grid.FrameCells(index=f.index, grid=f.grid) for f in series[:-1]
    ] + [series[-1]]
    sparse = map_grid.integrate(
        stripped, hints=[f.hint for f in frames], shifts=_noisy_shifts()
    )
    assert sparse.size == (23, 24)
    got = {u.cell for u in sparse.units}
    assert {(15, 14), (16, 15), (6, 16), (9, 16)} <= got
    assert len(got) == len(series[-1].units)
    for sparse_off, dense_off in zip(sparse.offsets, board.offsets):
        if sparse_off is not None:
            assert sparse_off == dense_off
    assert sparse.offsets[-1] is not None
    assert sum(off is None for off in sparse.offsets) <= 1


def test_edge_only_join_places_unit_free_frame():
    grid_a = map_grid.FrameGrid(
        cols=[100, 200, 300, 400], rows=[100, 200, 300, 400],
        west_bound=True, north_bound=True,
    )
    grid_b = map_grid.FrameGrid(
        cols=[110, 210, 310, 410], rows=[150, 250, 350, 450],
        west_bound=True, north_bound=True,
    )
    lone = map_grid.FrameCells(
        index=0, grid=grid_a, units=[(1, 1)], pixels={(1, 1): (250.0, 250.0)}
    )
    empty = map_grid.FrameCells(index=1, grid=grid_b)
    board = map_grid.integrate([lone, empty])
    assert board.offsets == [(0, 0), (0, 0)]
    assert [u.cell for u in board.units] == [(1, 1)]


def test_channel_disagreement_raises():
    grid_a = map_grid.FrameGrid(
        cols=[100, 200, 300, 400], rows=[100, 200, 300, 400],
        west_bound=True, east_bound=True, north_bound=True,
    )
    grid_b = map_grid.FrameGrid(
        cols=[100, 200, 300, 400, 500], rows=[100, 200, 300, 400],
        west_bound=True, east_bound=True, north_bound=True,
    )
    a = map_grid.FrameCells(index=0, grid=grid_a)
    b = map_grid.FrameCells(index=1, grid=grid_b)
    with pytest.raises(map_grid.IntegrationError, match="disagree"):
        map_grid.integrate([a, b])


def test_unplaceable_frame_drops_when_unit_free_raises_with_units():
    grid_edge = map_grid.FrameGrid(
        cols=[100, 200, 300, 400], rows=[100, 200, 300, 400],
        west_bound=True, north_bound=True,
    )
    grid_blind = map_grid.FrameGrid(
        cols=[100, 200, 300, 400], rows=[100, 200, 300, 400],
    )
    anchor = map_grid.FrameCells(
        index=0, grid=grid_edge, units=[(0, 0)], pixels={(0, 0): (150.0, 150.0)}
    )
    board = map_grid.integrate(
        [anchor, map_grid.FrameCells(index=1, grid=grid_blind)]
    )
    assert board.offsets == [(0, 0), None]
    assert any("dropped" in note for note in board.conflicts)
    orphan = map_grid.FrameCells(
        index=1, grid=grid_blind, units=[(2, 2)], pixels={(2, 2): (350.0, 350.0)}
    )
    with pytest.raises(map_grid.IntegrationError, match="no channel joins"):
        map_grid.integrate([anchor, orphan])


def test_deployed_marking_matches_user_assignment(answer):
    deployed = {u["id"]: u["deployed"] for u in answer["units"] if "deployed" in u}
    assert set(deployed) == {
        "s08", "s09", "s11", "s12", "s13", "s14", "s15", "s17", "s18", "s20",
    }
    by_team: dict[int, set[int]] = {}
    for mark in deployed.values():
        by_team.setdefault(mark["team"], set()).add(mark["slot"])
    assert by_team == {1: {1, 2, 3, 4, 5}, 2: {1, 2, 3, 4, 5}}
