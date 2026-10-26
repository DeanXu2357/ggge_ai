from dataclasses import dataclass

import pytest

from ggge_ai_2.interpreter.auto_cue import (
    AUTO_SCREENS,
    AutoCueInterpreter,
    auto_blue_fraction,
    auto_mode,
    auto_red_fraction,
)
from ggge_ai_2.interpreter.contract import AutoMode, Screen, Situation
from ggge_ai_2.stream.contract import Frame
from tests.ggge_ai_2.dataset import Case, cases, load_image

AUTO_CASES = [case for case in cases() if case.auto is not None]
SCREEN_VALUES = {screen.value for screen in Screen}
AUTO_SCREEN_VALUES = {screen.value for screen in AUTO_SCREENS}


@dataclass
class _FakeInner:
    situation: Situation | None

    def interpret(self, frame: Frame, candidates: frozenset[Screen]) -> Situation | None:
        return self.situation


def _frame(case: Case) -> Frame:
    return Frame(load_image(case), captured_at=1.0, seq=case.index)


@pytest.mark.parametrize("case", AUTO_CASES, ids=[case.id for case in AUTO_CASES])
def test_auto_mode_reads_the_labeled_mode(case: Case) -> None:
    image = load_image(case)

    assert auto_mode(image) is case.auto, (
        f"blue={auto_blue_fraction(image):.3f} red={auto_red_fraction(image):.3f}"
    )


@pytest.mark.parametrize("case", cases(), ids=[case.id for case in cases()])
def test_dataset_labels_auto_exactly_on_auto_screens(case: Case) -> None:
    on_auto_screen = case.screen in AUTO_SCREEN_VALUES

    assert (case.auto is not None) == on_auto_screen, (
        f"dataset error: screen {case.screen} has auto {case.auto}"
        f" but AUTO_SCREENS {'holds' if on_auto_screen else 'does not hold'} it"
    )


SCREEN_CASES = [case for case in cases() if case.screen in SCREEN_VALUES]


@pytest.mark.parametrize("case", SCREEN_CASES, ids=[case.id for case in SCREEN_CASES])
def test_sets_the_labeled_auto_mode_on_the_inner_screen(case: Case) -> None:
    screen = Screen(case.screen)
    assert (case.auto is not None) == (screen in AUTO_SCREENS), (
        f"dataset error: screen {case.screen} has auto {case.auto}"
    )
    inner = _FakeInner(Situation(case.index, screen))

    situation = AutoCueInterpreter(inner).interpret(_frame(case), frozenset())

    assert situation == Situation(case.index, screen, auto=case.auto)


def test_sets_none_outside_auto_screens() -> None:
    case = next(case for case in AUTO_CASES if case.auto is AutoMode.FULL)
    inner = _FakeInner(Situation(case.index, Screen.NON_PLAYER_PHASE_BATTLE_VIEW, AutoMode.FULL))

    situation = AutoCueInterpreter(inner).interpret(_frame(case), frozenset())

    assert situation == Situation(case.index, Screen.NON_PLAYER_PHASE_BATTLE_VIEW, auto=None)


def test_passes_none_through() -> None:
    frame = _frame(AUTO_CASES[0])

    assert AutoCueInterpreter(_FakeInner(None)).interpret(frame, frozenset()) is None
