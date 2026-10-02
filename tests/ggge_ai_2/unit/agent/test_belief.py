from __future__ import annotations

from ggge_ai_2.agent.belief import Belief, UiBasis, UiSource
from ggge_ai_2.agent.evidence import Sensed
from ggge_ai_2.stream.contract import NO_DISPLACEMENT, StillWindow
from ggge_ai_2.uisim.contract import UiState
from tests.ggge_ai_2.fakes.domain import FakeDomain
from tests.ggge_ai_2.fakes.mapgeom import NoMapGeometry
from tests.ggge_ai_2.fakes.uisim import FakeUiSim

ON_MAP = UiState("map", map_mode="hub")


def belief(ui: UiState) -> Belief:
    seen = UiBasis(UiSource.SEEN, frame_seq=1)
    return Belief(ui, seen, None, NO_DISPLACEMENT, FakeDomain(), StillWindow(0.5, 1.0, 1))


def after_sensing(before: Belief, sensed: Sensed) -> Belief:
    return before.sensed(sensed, FakeUiSim(), NoMapGeometry())


def test_unreadable_screens_keep_the_first_lost_frame():
    lost = Sensed(5, 1.0, StillWindow(4.5, 5.0, 5), 0.5, False, None, None, NO_DISPLACEMENT)
    again = Sensed(6, 5.0, StillWindow(5.5, 6.0, 6), 0.5, False, None, None, NO_DISPLACEMENT)
    after = after_sensing(after_sensing(belief(ON_MAP), lost), again)

    assert after.ui == ON_MAP
    assert after.ui_basis == UiBasis(UiSource.LOST, frame_seq=5)
