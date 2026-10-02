from __future__ import annotations

from dataclasses import dataclass

from ggge_ai_2.actuator.contract import Dispatch
from ggge_ai_2.agent.clock import Instant
from ggge_ai_2.interpreter.contract import Verdict
from ggge_ai_2.mapgeom.contract import BoardFact, BoardVerdict
from ggge_ai_2.mapparser.contract import MapReading
from ggge_ai_2.planner.contract import Step
from ggge_ai_2.stream.contract import Displacement, StillWindow
from ggge_ai_2.uisim.contract import Observed, Outcome, UiState


@dataclass(frozen=True)
class Sensed:
    frame_seq: int
    after: Instant
    still: StillWindow
    waited: float
    prediction_holds: bool
    observed: Observed | None
    map: MapReading | None
    displacement: Displacement


@dataclass(frozen=True)
class GuardFailed:
    step: Step
    premise: UiState | BoardFact
    verdict: Verdict | BoardVerdict
    frame_seq: int


@dataclass(frozen=True)
class Dispatched:
    step: Step
    dispatch: Dispatch
    frame_seq: int
    still: StillWindow | None
    outcome: Outcome | None
    displacement: Displacement
