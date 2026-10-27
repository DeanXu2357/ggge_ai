"""Tolerant layer: the unit and marker readings may miss or add items, because the play flow
corrects them later. These tests fail only when a rate falls below tolerance_baseline.json.

Update the baseline: uv run pytest tests/ggge_ai_2/unit/mapparser/test_ruled_map_tolerance.py
--update-tolerance-baseline
"""

from __future__ import annotations

import functools

import pytest

from ggge_ai_2.mapparser.contract import CellReading, MapReading, Marker
from ggge_ai_2.mapparser.opencv_parser import OpenCvMapParser
from ggge_ai_2.stream.contract import Frame
from tests.ggge_ai_2.dataset import cases, load_image
from tests.ggge_ai_2.unit.mapparser.tolerance import Tally, check_against_baseline

PARSER = OpenCvMapParser()
MAP_CASES = [case for case in cases() if case.map is not None]


# Keyed by the case ID because a Case holds a dict and does not hash.
@functools.cache
def _reading(case_id: str) -> MapReading:
    case = next(case for case in MAP_CASES if case.id == case_id)
    reading = PARSER.parse(Frame(load_image(case), 0.0, 0))
    assert reading is not None
    return reading


def test_reads_units_no_worse_than_the_baseline(pytestconfig: pytest.Config) -> None:
    tally = Tally()
    for case in MAP_CASES:
        reading = _reading(case.id)
        label = case.map
        assert label is not None
        read = {(unit.pos, unit.size) for unit in reading.units}
        tally.add(case.id, read=read, ruled=label.units)

    check_against_baseline(pytestconfig, "units", tally)


def test_reads_occupied_cells_no_worse_than_the_baseline(pytestconfig: pytest.Config) -> None:
    tally = Tally()
    for case in MAP_CASES:
        reading = _reading(case.id)
        label = case.map
        assert label is not None
        read = {cell for cell, value in reading.cells.items() if value is CellReading.OCCUPIED}
        tally.add(case.id, read=read, ruled=label.occupied & label.cells)

    check_against_baseline(pytestconfig, "occupied", tally)


@pytest.mark.parametrize("marker", list(Marker), ids=[marker.value for marker in Marker])
def test_reads_marker_cells_no_worse_than_the_baseline(
    pytestconfig: pytest.Config, marker: Marker
) -> None:
    tally = Tally()
    for case in MAP_CASES:
        reading = _reading(case.id)
        label = case.map
        assert label is not None
        read = {cell for cell, markers in reading.markers.items() if marker in markers}
        tally.add(case.id, read=read, ruled=label.markers[marker.value])

    check_against_baseline(pytestconfig, marker.value, tally)
