import functools

import pytest

from ggge_ai_2.interpreter.contract import Screen
from ggge_ai_2.interpreter.screens import QUICK_CHECKS
from tests.ggge_ai_2.dataset import cases, load_image

# Frames of another screen that pass a quick check. The user rules on each row.
FALSE_PASSES: dict[Screen, dict[str, str]] = {}

# Own frames that the section 2.4 elements cannot pass. The user rules on each row.
MISSES: dict[Screen, dict[str, str]] = {}


@functools.cache
def _passed() -> dict[str, frozenset[Screen]]:
    return {
        case.id: frozenset(
            screen for screen, check in QUICK_CHECKS.items() if check(load_image(case))
        )
        for case in cases()
        if case.power_save is None
    }


def _screen_of(case_id: str) -> str:
    return next(case.screen for case in cases() if case.id == case_id)


@pytest.mark.parametrize("screen", list(QUICK_CHECKS), ids=[s.value for s in QUICK_CHECKS])
def test_quick_check_passes_the_own_frames(screen: Screen) -> None:
    missed = {
        case_id
        for case_id, passed in _passed().items()
        if _screen_of(case_id) == screen.value and screen not in passed
    }

    assert missed == set(MISSES.get(screen, {}))


@pytest.mark.parametrize("screen", list(QUICK_CHECKS), ids=[s.value for s in QUICK_CHECKS])
def test_quick_check_passes_only_the_listed_frames_of_other_screens(screen: Screen) -> None:
    false_passes = {
        case_id
        for case_id, passed in _passed().items()
        if _screen_of(case_id) != screen.value and screen in passed
    }

    assert false_passes == set(FALSE_PASSES.get(screen, {}))


@pytest.mark.parametrize("screen", list(QUICK_CHECKS), ids=[s.value for s in QUICK_CHECKS])
def test_quick_check_has_own_frames(screen: Screen) -> None:
    assert any(_screen_of(case_id) == screen.value for case_id in _passed())
