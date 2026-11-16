from dataclasses import dataclass, field

import cv2
import pytest

from ggge_ai_2.interpreter.contract import Screen, Situation
from ggge_ai_2.interpreter.power_save_cue import (
    PowerSaveCueInterpreter,
    lock_icon_score,
    power_save_screen,
)
from ggge_ai_2.stream.contract import Frame
from tests.ggge_ai_2.dataset import Case, cases, load_image

POWER_SAVE_SCREENS = {"lock": Screen.POWER_SAVE_LOCK, "dim": Screen.POWER_SAVE_DIM, None: None}


@dataclass
class _FakeInner:
    situation: Situation | None
    calls: list[int] = field(default_factory=list[int])

    def interpret(self, frame: Frame, candidates: frozenset[Screen]) -> Situation | None:
        self.calls.append(frame.seq)
        return self.situation


def _frame(case: Case) -> Frame:
    return Frame(load_image(case), captured_at=1.0, seq=case.index)


@pytest.mark.parametrize("case", cases(), ids=[case.id for case in cases()])
def test_power_save_screen_reads_the_labeled_power_save(case: Case) -> None:
    image = load_image(case)

    assert power_save_screen(image) is POWER_SAVE_SCREENS[case.power_save], (
        f"gray_mean={cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).mean():.1f} lock_icon_score={lock_icon_score(image):.3f}"
    )


def test_power_save_frame_reads_without_the_inner() -> None:
    case = next(case for case in cases() if case.power_save == "lock")
    inner = _FakeInner(Situation(case.index, Screen.SERIES_LIST))

    situation = PowerSaveCueInterpreter(inner).interpret(_frame(case), frozenset())

    assert situation == Situation(case.index, Screen.POWER_SAVE_LOCK, None)
    assert inner.calls == []


def test_other_frame_goes_to_the_inner() -> None:
    case = next(case for case in cases() if case.power_save is None)
    inner = _FakeInner(Situation(case.index, Screen.SERIES_LIST))

    situation = PowerSaveCueInterpreter(inner).interpret(_frame(case), frozenset())

    assert situation == Situation(case.index, Screen.SERIES_LIST)
    assert inner.calls == [case.index]
