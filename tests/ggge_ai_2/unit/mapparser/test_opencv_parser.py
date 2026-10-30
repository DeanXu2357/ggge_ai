import pytest

from ggge_ai_2.interpreter.contract import Screen
from ggge_ai_2.mapparser.opencv_parser import OpenCvMapParser
from ggge_ai_2.stream.contract import Frame
from tests.ggge_ai_2.dataset import Case, cases, load_image

PARSER = OpenCvMapParser()
# These overview frames show no grid lines: the second stage of the recording and run
# 20261024-183527.
GRID_OFF_IDS = frozenset(
    {"rec20261014-1585", "rec20261014-1645", "rec20261014-1691", "run20261024-183527-15"}
)
GRID_OFF_CASES = [case for case in cases() if case.id in GRID_OFF_IDS]
# The user ruled that the parser reads no map on the battle prep screens and in the phases
# of the other factions, although these frames show the grid.
RULED_OUT_SCREENS = frozenset(
    {
        Screen.BATTLE_PREP_ATTACK,
        Screen.BATTLE_PREP_RESPONSE_ATTACK,
        Screen.NON_PLAYER_PHASE_BATTLE_VIEW,
    }
)
RULED_OUT_CASES = [
    case for case in cases() if case.screen in {screen.value for screen in RULED_OUT_SCREENS}
]


def _frame(case: Case) -> Frame:
    return Frame(load_image(case), 0.0, case.index)


@pytest.mark.parametrize("case", GRID_OFF_CASES, ids=[case.id for case in GRID_OFF_CASES])
def test_parse_reads_nothing_on_a_map_screen_without_grid(case: Case) -> None:
    assert PARSER.parse(_frame(case), Screen(case.screen)) is None


@pytest.mark.parametrize("case", GRID_OFF_CASES, ids=[case.id for case in GRID_OFF_CASES])
def test_locate_gives_no_point_on_a_map_screen_without_grid(case: Case) -> None:
    assert PARSER.locate(_frame(case), (0, 0)) is None


@pytest.mark.parametrize("case", RULED_OUT_CASES, ids=[case.id for case in RULED_OUT_CASES])
def test_parse_reads_nothing_on_the_screens_that_the_user_ruled_out(case: Case) -> None:
    assert PARSER.parse(_frame(case), Screen(case.screen)) is None
