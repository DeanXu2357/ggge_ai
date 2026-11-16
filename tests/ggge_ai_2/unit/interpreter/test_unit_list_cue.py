from dataclasses import dataclass

import pytest

from ggge_ai_2.interpreter.contract import Screen, Situation, UnitList
from ggge_ai_2.interpreter.unit_list_cue import UnitListCueInterpreter
from ggge_ai_2.stream.contract import Frame
from tests.ggge_ai_2.dataset import Case, cases, load_image

RULED = [case for case in cases() if case.elements.get("unit_list") is not None]


@dataclass
class _FakeInner:
    situation: Situation | None

    def interpret(self, frame: Frame, candidates: frozenset[Screen]) -> Situation | None:
        return self.situation


def _frame(case: Case) -> Frame:
    return Frame(load_image(case), captured_at=1.0, seq=case.index)


def _expected(ruling: str | None) -> UnitList | None:
    return None if ruling in (None, "absent") else UnitList(ruling)


@pytest.mark.parametrize("case", RULED, ids=[case.id for case in RULED])
def test_sets_the_ruled_unit_list_on_the_overview(case: Case) -> None:
    inner = _FakeInner(Situation(case.index, Screen(case.screen)))

    situation = UnitListCueInterpreter(inner).interpret(_frame(case), frozenset())

    assert situation is not None
    assert situation.unit_list is _expected(case.elements["unit_list"])


def test_sets_none_outside_the_overview() -> None:
    case = next(case for case in RULED if case.elements["unit_list"] == "open")
    inner = _FakeInner(Situation(case.index, Screen.SELECT_ACTION_IN_BATTLE))

    situation = UnitListCueInterpreter(inner).interpret(_frame(case), frozenset())

    assert situation == Situation(case.index, Screen.SELECT_ACTION_IN_BATTLE)


def test_passes_none_through() -> None:
    frame = _frame(RULED[0])

    assert UnitListCueInterpreter(_FakeInner(None)).interpret(frame, frozenset()) is None
