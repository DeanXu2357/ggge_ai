from __future__ import annotations

from dataclasses import replace

from ggge_ai_2.agent.belief import Belief, Passing, ScreenLock, Sensed, UiBasis, UiSource
from ggge_ai_2.stream.contract import StillWindow
from ggge_ai_2.uisim.contract import Observed, UiScreen, UiState
from tests.ggge_ai_2.fakes.domain import FakeDomain
from tests.ggge_ai_2.fakes.uisim import FakeUiSim

LIST = UiState(UiScreen.STORY_STAGE_LIST)
ON_MAP = UiState(UiScreen.PLAYER_PHASE_OVERVIEW)


def window(seq: int) -> StillWindow:
    return StillWindow(seq - 0.5, float(seq), seq)


def sensed(seq: int, observed: Observed | None = None) -> Sensed:
    return Sensed(window(seq), observed, None)


def start(ui: UiState = UiState(UiScreen.STAGE_CHOSEN)) -> Belief:
    return Belief(ui, UiBasis(UiSource.ASSUMED), FakeDomain(), None)


def test_recognized_frame_syncs_the_ui_and_marks_it_seen():
    belief = start().update(sensed(1, Observed(UiScreen.STORY_STAGE_LIST)), FakeUiSim())

    assert belief.ui == LIST
    assert belief.ui_basis == UiBasis(UiSource.SEEN, 1)
    assert belief.as_of == window(1)


def test_unreadable_frames_keep_the_ui_and_the_first_lost_frame():
    lost = start(ON_MAP).update(sensed(5), FakeUiSim())
    after = lost.update(sensed(6), FakeUiSim())

    assert after.ui == ON_MAP
    assert after.ui_basis == UiBasis(UiSource.LOST, 5)
    assert after.as_of == window(6)


def test_locked_frame_records_the_lock_and_keeps_the_rest_of_the_belief():
    seen = start().update(sensed(1, Observed(UiScreen.STORY_STAGE_LIST)), FakeUiSim())
    lock = Sensed(window(2), None, None, ScreenLock.ICON)
    locked = seen.update(lock, FakeUiSim())

    assert locked == replace(seen, screen_lock=ScreenLock.ICON, as_of=window(2))


def test_readable_frame_after_a_lock_clears_the_lock():
    locked = replace(start(), screen_lock=ScreenLock.DIM)
    after = locked.update(sensed(3, Observed(UiScreen.STORY_STAGE_LIST)), FakeUiSim())

    assert after.screen_lock is None


def test_passing_frame_records_the_passing_and_keeps_the_rest_of_the_belief():
    seen = start().update(sensed(1, Observed(UiScreen.STORY_STAGE_LIST)), FakeUiSim())
    loading = Sensed(window(2), None, None, passing=Passing.WAIT)
    passing = seen.update(loading, FakeUiSim())

    assert passing == replace(seen, passing=Passing.WAIT, as_of=window(2))


def test_readable_frame_after_a_passing_frame_clears_the_passing():
    passing = replace(start(), passing=Passing.TAP_TO_CONTINUE)
    after = passing.update(sensed(3, Observed(UiScreen.STORY_STAGE_LIST)), FakeUiSim())

    assert after.passing is None
    assert after.ui == LIST
