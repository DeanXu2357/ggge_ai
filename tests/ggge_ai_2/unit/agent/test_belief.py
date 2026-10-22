from __future__ import annotations

from dataclasses import dataclass, field, replace

from ggge_ai_2.agent.belief import Belief, ScreenLock, Sensed, UiBasis, UiSource
from ggge_ai_2.mapgeom.contract import Alignment, CellContent, KnownMap, LocalBoard
from ggge_ai_2.stream.contract import StillWindow
from ggge_ai_2.uisim.contract import Observed, UiMapMode, UiScreen, UiState
from tests.ggge_ai_2.fakes.domain import FakeDomain
from tests.ggge_ai_2.fakes.mapgeom import NoMapGeometry
from tests.ggge_ai_2.fakes.uisim import FakeUiSim

LIST = UiState(UiScreen.STORY_STAGE_LIST)
ON_MAP = UiState(UiScreen.PLAYER_PHASE_OVERVIEW, map_mode=UiMapMode.HUB)
BOARD = LocalBoard({(2, 2): CellContent.EMPTY}, frozenset())


def window(seq: int) -> StillWindow:
    return StillWindow(seq - 0.5, float(seq), seq)


def sensed(seq: int, observed: Observed | None = None, board: LocalBoard | None = None) -> Sensed:
    return Sensed(window(seq), observed, board)


def start(ui: UiState = UiState(UiScreen.STAGE_CHOSEN)) -> Belief:
    return Belief(ui, UiBasis(UiSource.ASSUMED), None, KnownMap({}), FakeDomain(), None)


@dataclass
class FixedGeometry:
    shift: tuple[int, int]
    priors: list[Alignment | None] = field(default_factory=list)

    def align(self, board: LocalBoard, known: KnownMap, prior: Alignment | None) -> Alignment:
        self.priors.append(prior)
        return Alignment(self.shift)

    def merge(self, known: KnownMap, board: LocalBoard, alignment: Alignment) -> KnownMap:
        dx, dy = alignment.shift
        seen = {(x + dx, y + dy): content for (x, y), content in board.cells.items()}
        return KnownMap({**known.cells, **seen})


class NoPlaceGeometry:
    def align(self, board: LocalBoard, known: KnownMap, prior: Alignment | None) -> None:
        return None

    def merge(self, known: KnownMap, board: LocalBoard, alignment: Alignment) -> KnownMap:
        raise AssertionError("nothing to merge without an alignment")


def test_recognized_frame_syncs_the_ui_and_marks_it_seen():
    belief = start().update(
        sensed(1, Observed(UiScreen.STORY_STAGE_LIST)), FakeUiSim(), NoMapGeometry()
    )

    assert belief.ui == LIST
    assert belief.ui_basis == UiBasis(UiSource.SEEN, 1)
    assert belief.as_of == window(1)


def test_unreadable_frames_keep_the_ui_and_the_first_lost_frame():
    lost = start(ON_MAP).update(sensed(5), FakeUiSim(), NoMapGeometry())
    after = lost.update(sensed(6), FakeUiSim(), NoMapGeometry())

    assert after.ui == ON_MAP
    assert after.ui_basis == UiBasis(UiSource.LOST, 5)
    assert after.as_of == window(6)


def test_board_puts_the_alignment_and_the_merged_map_into_the_belief():
    geometry = FixedGeometry((10, 5))
    belief = start().update(sensed(1, board=BOARD), FakeUiSim(), geometry)

    assert geometry.priors == [None]
    assert belief.camera == Alignment((10, 5))
    assert belief.known_map == KnownMap({(12, 7): CellContent.EMPTY})


def test_frame_without_a_board_keeps_the_camera_and_the_map():
    seen = start().update(sensed(1, board=BOARD), FakeUiSim(), FixedGeometry((10, 5)))
    after = seen.update(sensed(2), FakeUiSim(), NoMapGeometry())

    assert after.camera == Alignment((10, 5))
    assert after.known_map == seen.known_map


def test_board_with_no_place_on_the_known_map_keeps_the_camera_and_the_map():
    seen = start().update(sensed(1, board=BOARD), FakeUiSim(), FixedGeometry((10, 5)))
    after = seen.update(sensed(2, board=BOARD), FakeUiSim(), NoPlaceGeometry())

    assert after.camera == Alignment((10, 5))
    assert after.known_map == seen.known_map


def test_locked_frame_records_the_lock_and_keeps_the_rest_of_the_belief():
    seen = start().update(sensed(1, board=BOARD), FakeUiSim(), FixedGeometry((10, 5)))
    lock = Sensed(window(2), None, None, ScreenLock.ICON)
    locked = seen.update(lock, FakeUiSim(), NoMapGeometry())

    assert locked == replace(seen, screen_lock=ScreenLock.ICON, as_of=window(2))


def test_readable_frame_after_a_lock_clears_the_lock():
    locked = replace(start(), screen_lock=ScreenLock.DIM)
    after = locked.update(
        sensed(3, Observed(UiScreen.STORY_STAGE_LIST)), FakeUiSim(), NoMapGeometry()
    )

    assert after.screen_lock is None
