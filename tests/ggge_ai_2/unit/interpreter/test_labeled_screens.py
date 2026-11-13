import functools

import pytest

from ggge_ai_2.interpreter.elements.detectors import DETECTORS
from ggge_ai_2.screenmodel.contract import ModelScreen, ScreenJudgment
from ggge_ai_2.screenmodel.definition_model import DefinitionScreenModel
from tests.ggge_ai_2.dataset import cases, load_image

MODEL = DefinitionScreenModel()
SCREENS = [definition.screen for definition in MODEL.definitions]

# Frames of another screen that the definition of a screen matches. The user rules on each row.
FALSE_MATCHES: dict[ModelScreen, dict[str, str]] = {}

# Own frames that the screen model does not judge as their screen. The user rules on each row.
MISSES: dict[ModelScreen, dict[str, str]] = {}


@functools.cache
def _judgments() -> dict[str, ScreenJudgment]:
    judgments: dict[str, ScreenJudgment] = {}
    for case in cases():
        if case.power_save is not None:
            continue
        image = load_image(case)
        judgments[case.id] = MODEL.judge(
            [found for detector in DETECTORS for found in detector.detect(image)]
        )
    return judgments


def _screen_of(case_id: str) -> str:
    return next(case.screen for case in cases() if case.id == case_id)


@pytest.mark.parametrize("screen", SCREENS, ids=[screen.value for screen in SCREENS])
def test_judges_the_own_frames_as_the_screen(screen: ModelScreen) -> None:
    missed = {
        case_id
        for case_id, judgment in _judgments().items()
        if _screen_of(case_id) == screen.value and judgment.screen is not screen
    }

    assert missed == set(MISSES.get(screen, {}))


@pytest.mark.parametrize("screen", SCREENS, ids=[screen.value for screen in SCREENS])
def test_matches_only_the_listed_frames_of_other_screens(screen: ModelScreen) -> None:
    false_matches = {
        case_id
        for case_id, judgment in _judgments().items()
        if _screen_of(case_id) != screen.value and screen in judgment.matched
    }

    assert false_matches == set(FALSE_MATCHES.get(screen, {}))


@pytest.mark.parametrize("screen", SCREENS, ids=[screen.value for screen in SCREENS])
def test_has_own_frames(screen: ModelScreen) -> None:
    assert any(_screen_of(case_id) == screen.value for case_id in _judgments())
