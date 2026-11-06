import logging

import numpy as np
import pytest

from ggge_ai_2.interpreter.contract import Screen, Situation
from ggge_ai_2.interpreter.opencv import OpenCvInterpreter
from ggge_ai_2.interpreter.screens import QuickCheck
from ggge_ai_2.stream.contract import Frame
from tests.ggge_ai_2.dataset import cases, load_image

FRAME = Frame(np.zeros((1080, 2340, 3), np.uint8), captured_at=1.0, seq=7)


def _always(result: bool) -> QuickCheck:
    return lambda image: result


def _never_called(image: np.ndarray) -> bool:
    raise AssertionError("the check of a screen outside the candidates ran")


def test_returns_the_one_candidate_that_passes() -> None:
    interpreter = OpenCvInterpreter(
        {
            Screen.SELECT_ACTION_IN_BATTLE: _always(True),
            Screen.SELECT_WEAPON_IN_BATTLE: _always(False),
            Screen.BATTLE_PREP_ATTACK: _never_called,
        }
    )

    situation = interpreter.interpret(
        FRAME, frozenset({Screen.SELECT_ACTION_IN_BATTLE, Screen.SELECT_WEAPON_IN_BATTLE})
    )

    assert situation == Situation(7, Screen.SELECT_ACTION_IN_BATTLE)


def test_returns_none_and_logs_when_no_candidate_passes(caplog: pytest.LogCaptureFixture) -> None:
    interpreter = OpenCvInterpreter({Screen.SELECT_ACTION_IN_BATTLE: _always(False)})

    with caplog.at_level(logging.INFO):
        situation = interpreter.interpret(
            FRAME, frozenset({Screen.SELECT_ACTION_IN_BATTLE, Screen.LOADING})
        )

    assert situation is None
    record = caplog.records[-1]
    assert getattr(record, "frame_seq") == 7
    assert getattr(record, "passed") == []
    assert getattr(record, "candidates") == ["loading", "select_action_in_battle"]


def test_returns_none_and_logs_when_two_candidates_pass(caplog: pytest.LogCaptureFixture) -> None:
    interpreter = OpenCvInterpreter(
        {
            Screen.SELECT_ACTION_IN_BATTLE: _always(True),
            Screen.SELECT_WEAPON_IN_BATTLE: _always(True),
        }
    )

    with caplog.at_level(logging.INFO):
        situation = interpreter.interpret(
            FRAME, frozenset({Screen.SELECT_ACTION_IN_BATTLE, Screen.SELECT_WEAPON_IN_BATTLE})
        )

    assert situation is None
    assert getattr(caplog.records[-1], "passed") == [
        "select_action_in_battle",
        "select_weapon_in_battle",
    ]


def test_reads_a_labeled_frame_among_the_battle_candidates() -> None:
    case = next(case for case in cases() if case.id == "rec20261014-648")
    frame = Frame(load_image(case), captured_at=1.0, seq=case.index)
    candidates = frozenset(
        {
            Screen.SELECT_WEAPON_IN_BATTLE,
            Screen.BATTLE_PREP_ATTACK,
            Screen.BATTLE_PREP_RESPONSE_ATTACK,
            Screen.BATTLE_MAIN_SETTING,
        }
    )

    assert OpenCvInterpreter().interpret(frame, candidates) == Situation(
        case.index, Screen.BATTLE_PREP_ATTACK
    )
