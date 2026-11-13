import pytest

from ggge_ai_2.mapparser.opencv_parser import OpenCvMapParser
from ggge_ai_2.stream.contract import Frame
from tests.ggge_ai_2.dataset import Case, cases, load_image
from tests.ggge_ai_2.unit.mapparser.scope import scope_of

PARSER = OpenCvMapParser()
# These overview frames show no grid lines: the second stage of the recording and run
# 20261024-183527.
GRID_OFF_IDS = frozenset(
    {"rec20261014-1585", "rec20261014-1645", "rec20261014-1691", "run20261024-183527-15"}
)
GRID_OFF_CASES = [case for case in cases() if case.id in GRID_OFF_IDS]


def _frame(case: Case) -> Frame:
    return Frame(load_image(case), 0.0, case.index)


@pytest.mark.parametrize("case", GRID_OFF_CASES, ids=[case.id for case in GRID_OFF_CASES])
def test_parse_reads_nothing_on_a_map_screen_without_grid(case: Case) -> None:
    assert PARSER.parse(_frame(case), scope_of(case)) is None
