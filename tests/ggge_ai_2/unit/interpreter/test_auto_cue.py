from dataclasses import dataclass

import cv2
import numpy as np

from ggge_ai_2.interpreter.auto_cue import (
    AUTO_RECT,
    AutoCueInterpreter,
    auto_blue_fraction,
    auto_mode,
    auto_red_fraction,
)
from ggge_ai_2.interpreter.contract import AutoMode, Screen, Situation
from ggge_ai_2.stream.contract import Frame

BLUE = (230, 160, 40)
RED = (70, 60, 200)
WHITE = (230, 230, 230)
GRAY = (60, 60, 60)


def _frame_image(auto_color: tuple[int, int, int]) -> np.ndarray:
    image = np.zeros((1080, 2340, 3), dtype=np.uint8)
    left, top, right, bottom = AUTO_RECT
    image[int(top * 1080) : int(bottom * 1080), int(left * 2340) : int(right * 2340)] = auto_color
    return image


@dataclass
class _FakeInner:
    situation: Situation | None

    def interpret(self, frame: Frame, candidates: frozenset[Screen]) -> Situation | None:
        return self.situation


def test_blue_sample_is_inside_the_hsv_band() -> None:
    hue, sat, val = cv2.cvtColor(np.array([[BLUE]], dtype=np.uint8), cv2.COLOR_BGR2HSV)[0, 0]
    assert 90 <= hue <= 115
    assert sat > 120
    assert val > 150


def test_red_sample_is_inside_the_hsv_band() -> None:
    hue, sat, val = cv2.cvtColor(np.array([[RED]], dtype=np.uint8), cv2.COLOR_BGR2HSV)[0, 0]
    assert hue <= 10 or hue >= 160
    assert sat > 100
    assert val > 120


def test_blue_button_reads_full() -> None:
    image = _frame_image(BLUE)
    assert auto_blue_fraction(image) == 1.0
    assert auto_red_fraction(image) == 0.0
    assert auto_mode(image) is AutoMode.FULL


def test_red_button_reads_semi() -> None:
    image = _frame_image(RED)
    assert auto_blue_fraction(image) == 0.0
    assert auto_red_fraction(image) == 1.0
    assert auto_mode(image) is AutoMode.SEMI


def test_white_and_gray_buttons_read_manual() -> None:
    for color in (WHITE, GRAY):
        image = _frame_image(color)
        assert auto_blue_fraction(image) == 0.0
        assert auto_red_fraction(image) == 0.0
        assert auto_mode(image) is AutoMode.MANUAL


def test_overrides_inner_auto_on_an_auto_screen() -> None:
    inner = _FakeInner(Situation(7, Screen.PLAYER_PHASE_OVERVIEW, auto=AutoMode.FULL))
    frame = Frame(_frame_image(GRAY), captured_at=1.0, seq=7)

    situation = AutoCueInterpreter(inner).interpret(frame, frozenset())

    assert situation == Situation(7, Screen.PLAYER_PHASE_OVERVIEW, auto=AutoMode.MANUAL)


def test_reads_semi_on_an_auto_screen() -> None:
    inner = _FakeInner(Situation(7, Screen.BATTLE_PREP_ATTACK, auto=None))
    frame = Frame(_frame_image(RED), captured_at=1.0, seq=7)

    situation = AutoCueInterpreter(inner).interpret(frame, frozenset())

    assert situation == Situation(7, Screen.BATTLE_PREP_ATTACK, auto=AutoMode.SEMI)


def test_sets_none_outside_auto_screens() -> None:
    inner = _FakeInner(Situation(7, Screen.NON_PLAYER_PHASE_BATTLE_VIEW, auto=AutoMode.FULL))
    frame = Frame(_frame_image(BLUE), captured_at=1.0, seq=7)

    situation = AutoCueInterpreter(inner).interpret(frame, frozenset())

    assert situation == Situation(7, Screen.NON_PLAYER_PHASE_BATTLE_VIEW, auto=None)


def test_passes_none_through() -> None:
    frame = Frame(_frame_image(BLUE), captured_at=1.0, seq=7)

    assert AutoCueInterpreter(_FakeInner(None)).interpret(frame, frozenset()) is None
