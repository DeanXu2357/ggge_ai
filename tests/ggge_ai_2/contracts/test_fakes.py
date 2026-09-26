from itertools import count

from ggge_ai_2.actuator.contract import Tap, TouchPoint
from ggge_ai_2.uisim.contract import MapMode, Operation, Outcome, Screen, ScreenIs, UiState
from tests.ggge_ai_2.contracts.actuator import ActuatorContract
from tests.ggge_ai_2.contracts.interpreter import InterpreterContract
from tests.ggge_ai_2.contracts.mapgeom import ProjectionContract
from tests.ggge_ai_2.contracts.stream import StreamContract
from tests.ggge_ai_2.contracts.uisim import UiSimContract
from tests.ggge_ai_2.fakes.actuator import RecordingActuator
from tests.ggge_ai_2.fakes.interpreter import LabeledInterpreter
from tests.ggge_ai_2.fakes.mapgeom import GridProjection
from tests.ggge_ai_2.fakes.stream import TimelineStream, frames
from tests.ggge_ai_2.fakes.uisim import FrozenUiSim

ON_MAP = UiState(Screen.BATTLE_MAP, map_mode=MapMode.HUB)
DETAIL = UiState(Screen.UNIT_DETAIL)


class TestTimelineStream(StreamContract):
    def make(self, timeline):
        return TimelineStream(timeline)


class TestLabeledInterpreter(InterpreterContract):
    def make(self):
        return LabeledInterpreter({1: ON_MAP})

    def known_frame(self):
        return frames((0.1, 1))[0], ON_MAP

    def unknown_frame(self):
        return frames((0.1, 9))[0]


class TestFrozenUiSim(UiSimContract):
    def make(self):
        open_detail = Operation(
            "open_detail",
            (ScreenIs(Screen.BATTLE_MAP),),
            Tap(TouchPoint(1200, 600)),
            (Outcome("detail", ScreenIs(Screen.UNIT_DETAIL), DETAIL),),
            2.0,
            1.0,
        )
        return FrozenUiSim(ON_MAP, {ON_MAP: (open_detail,)})


class TestGridProjection(ProjectionContract):
    def make(self):
        return GridProjection(frame_seq=1, shift=(10, 5))

    def visible_cells(self):
        return [(12, 7), (13, 7), (14, 8)]


class TestRecordingActuator(ActuatorContract):
    def make(self):
        ticks = count()
        return RecordingActuator(clock=lambda: float(next(ticks)))

    def sent(self, actuator):
        return actuator.sent
