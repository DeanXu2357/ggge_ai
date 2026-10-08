from __future__ import annotations

from ggge_ai_2.agent.loop import Belief, UiBasis, UiSource
from ggge_ai_2.mapgeom.contract import KnownMap
from ggge_ai_2.stream.contract import StillWindow
from ggge_ai_2.uisim.contract import UiMapMode, UiScreen, UiState
from tests.ggge_ai_2.fakes.domain import FakeDomain
from tests.ggge_ai_2.fakes.mapgeom import NoMapGeometry
from tests.ggge_ai_2.fakes.uisim import FakeUiSim

ON_MAP = UiState(UiScreen.BATTLE_MAP, map_mode=UiMapMode.HUB)


def belief(ui: UiState) -> Belief:
    seen = UiBasis(UiSource.SEEN, frame_seq=1)
    return Belief(ui, seen, None, KnownMap({}), FakeDomain(), StillWindow(0.5, 1.0, 1))


def after_an_unreadable_frame(before: Belief, still: StillWindow) -> Belief:
    return before.revise_when_sensed(still, None, None, FakeUiSim(), NoMapGeometry())


def test_unreadable_screens_keep_the_first_lost_frame():
    lost = after_an_unreadable_frame(belief(ON_MAP), StillWindow(4.5, 5.0, 5))
    after = after_an_unreadable_frame(lost, StillWindow(5.5, 6.0, 6))

    assert after.ui == ON_MAP
    assert after.ui_basis == UiBasis(UiSource.LOST, frame_seq=5)
