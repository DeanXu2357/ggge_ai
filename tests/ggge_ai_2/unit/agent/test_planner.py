from __future__ import annotations

from dataclasses import dataclass, replace

from ggge_ai_2.agent.contract import (
    ActionResult,
    ActionStatus,
    CellReads,
    Finish,
    Sensed,
    Step,
    Wait,
)
from ggge_ai_2.agent.planner import (
    GRID_SHOWN,
    LEFT,
    READY,
    STAGE_INFO,
    Belief,
    Memory,
    RulePlanner,
    UiBasis,
    UiSource,
)
from ggge_ai_2.mapgeom.contract import Alignment, KnownMap, LocalBoard
from ggge_ai_2.mapparser.contract import CellReading, MapReading
from ggge_ai_2.planner.mapsync.contract import Explored, Probe
from ggge_ai_2.stream.contract import StillWindow
from ggge_ai_2.uisim.contract import (
    DangerBand,
    Observed,
    Operation,
    Outcome,
    RatioRect,
    UiAuto,
    UiMapMode,
    UiOverlay,
    UiScreen,
    UiState,
    UiTap,
)
from tests.ggge_ai_2.fakes.uisim import FakeUiSim

MAP_BAND = DangerBand((RatioRect(0.0, 0.0, 0.1, 0.1),))
READY_SEEN = Observed(UiScreen.BATTLE_MAP, map_mode=UiMapMode.HUB, auto=UiAuto.OFF, grid_shown=True)
READING = MapReading({(2, 2): CellReading.EMPTY}, frozenset())


def shift(state: UiState, goal: UiState) -> Operation:
    return Operation("shift", state, UiTap((0.5, 0.5)), (Outcome("arrived", goal),), 2.0, 1.0)


def tap_map(state: UiState) -> Operation:
    return Operation("tap_map", state, UiTap((0.5, 0.5)), (), 2.0, 1.0)


@dataclass(frozen=True)
class FakeUiShift:
    reachable: bool = True

    def next(self, state: UiState, goal: UiState) -> Operation | None:
        return shift(state, goal) if self.reachable else None

    def tap_map(self, state: UiState) -> Operation | None:
        return tap_map(state)


@dataclass(frozen=True)
class FakeMapSync:
    decision: Probe | Explored | None = None

    def next(self, known: KnownMap, camera: Alignment) -> Probe | Explored | None:
        return self.decision


class FixedGeometry:
    def align(self, board: LocalBoard, known: KnownMap, prior: Alignment | None) -> Alignment:
        return Alignment((10, 5))

    def merge(self, known: KnownMap, board: LocalBoard, alignment: Alignment) -> KnownMap:
        dx, dy = alignment.shift
        seen = {(x + dx, y + dy): content for (x, y), content in board.cells.items()}
        return KnownMap({**known.cells, **seen})


def make_planner(decision=None, reachable=True, recorded=None) -> RulePlanner:
    return RulePlanner(
        uisim=FakeUiSim({UiScreen.BATTLE_MAP: MAP_BAND}),
        mapgeom=FixedGeometry(),
        uishift=FakeUiShift(reachable),
        mapsync=FakeMapSync(decision),
        recorded=recorded,
    )


def start() -> Memory:
    ui = UiState(UiScreen.LOGIN_BONUS)
    return Memory(Belief(ui, UiBasis(UiSource.ASSUMED), None, KnownMap({}), None))


def sensed(observed: Observed | None, reading: MapReading | None = None) -> Sensed:
    return Sensed(StillWindow(0.5, 1.0, 1), observed, reading)


def goal_of(decision: Step | Wait | Finish) -> UiState:
    assert isinstance(decision, Step)
    return decision.operation.outcomes[0].then


def test_unreadable_screen_halts():
    decision, _ = make_planner().plan(start(), sensed(None), None)

    assert decision is Finish.HALTED


def test_blocked_gesture_halts():
    step = Step(tap_map(READY), (), DangerBand())
    blocked = ActionResult(step, ActionStatus.BLOCKED)

    decision, _ = make_planner().plan(start(), sensed(READY_SEEN), blocked)

    assert decision is Finish.HALTED


def test_dialog_is_closed_first():
    covered = Observed(UiScreen.STAGE_LIST, frozenset({UiOverlay.DIALOG}))

    decision, _ = make_planner().plan(start(), sensed(covered), None)

    assert goal_of(decision) == UiState(UiScreen.STAGE_LIST)


def test_outside_the_map_the_planner_heads_for_a_ready_map():
    decision, _ = make_planner().plan(start(), sensed(Observed(UiScreen.STAGE_LIST)), None)

    assert goal_of(decision) == READY


def test_auto_left_on_restarts_the_stage():
    running = replace(READY_SEEN, auto=UiAuto.ON)
    on = UiState(UiScreen.BATTLE_MAP, map_mode=UiMapMode.HUB, auto=UiAuto.ON, grid_shown=True)

    decision, memory = make_planner().plan(start(), sensed(running), None)

    assert goal_of(decision) == replace(on, auto=UiAuto.OFF)
    assert memory.goals == (replace(on, auto=UiAuto.OFF), GRID_SHOWN, STAGE_INFO, READY)


def test_hidden_grid_is_shown_before_the_map_is_read():
    hidden = replace(READY_SEEN, grid_shown=False)

    decision, memory = make_planner().plan(start(), sensed(hidden), None)

    assert goal_of(decision) == GRID_SHOWN
    assert memory.goals == (GRID_SHOWN, READY)


def test_reached_goal_is_dropped():
    memory = replace(start(), goals=(GRID_SHOWN, READY))
    settings = Observed(UiScreen.BATTLE_SETTINGS, grid_shown=True)

    decision, memory = make_planner().plan(memory, sensed(settings), None)

    assert goal_of(decision) == READY
    assert memory.goals == (READY,)


def test_selected_unit_goes_back_to_the_hub():
    selected = replace(READY_SEEN, map_mode=UiMapMode.SELECTED)

    decision, _ = make_planner().plan(start(), sensed(selected), None)

    assert goal_of(decision) == READY


def test_probe_taps_the_view_cell_of_the_world_cell():
    planner = make_planner(Probe((12, 7)))

    decision, memory = planner.plan(start(), sensed(READY_SEEN, READING), None)

    assert isinstance(decision, Step)
    assert decision.operation.name == "tap_map"
    assert decision.target == (2, 2)
    assert decision.map_premise == (CellReads((2, 2), CellReading.EMPTY),)
    assert decision.band == MAP_BAND
    assert memory.belief.camera == Alignment((10, 5))


def test_explored_map_is_left_and_then_the_run_is_done():
    planner = make_planner(Explored())

    decision, memory = planner.plan(start(), sensed(READY_SEEN, READING), None)
    assert goal_of(decision) == LEFT
    assert memory.explored

    decision, _ = planner.plan(memory, sensed(Observed(UiScreen.STAGE_LIST)), None)
    assert decision is Finish.DONE


def test_no_cell_in_view_halts_until_the_pan_exists():
    decision, _ = make_planner(None).plan(start(), sensed(READY_SEEN, READING), None)

    assert decision is Finish.HALTED


def test_map_without_an_alignment_waits():
    decision, _ = make_planner(Probe((12, 7))).plan(start(), sensed(READY_SEEN), None)

    assert isinstance(decision, Wait)


def test_recorded_map_halts_until_the_battle_plan_exists():
    planner = make_planner(recorded=KnownMap({}))

    decision, _ = planner.plan(start(), sensed(READY_SEEN), None)

    assert decision is Finish.HALTED


def test_unreachable_goal_halts():
    decision, _ = make_planner(reachable=False).plan(
        start(), sensed(Observed(UiScreen.STAGE_LIST)), None
    )

    assert decision is Finish.HALTED


def test_verified_outcome_becomes_the_prediction():
    step = Step(shift(UiState(UiScreen.STAGE_LIST), STAGE_INFO), (), DangerBand())
    arrived = step.operation.outcomes[0]
    verified = ActionResult(step, ActionStatus.VERIFIED, outcome=arrived)

    belief = start().belief.revise_when_acted(verified, FakeUiSim())

    assert belief.ui == STAGE_INFO
    assert belief.ui_basis == UiBasis(UiSource.PREDICTED, outcome="arrived")


def test_actions_that_keep_failing_halt():
    step = Step(shift(UiState(UiScreen.STAGE_LIST), READY), (), DangerBand())
    missed = ActionResult(step, ActionStatus.UNVERIFIED)
    planner = make_planner()
    memory = replace(start(), strikes=2)
    decision, memory = planner.plan(memory, sensed(Observed(UiScreen.STAGE_LIST)), missed)

    assert decision is Finish.HALTED


def test_a_verified_dialog_close_does_not_hide_a_failing_entry():
    entry = Step(shift(UiState(UiScreen.STAGE_LIST), READY), (), DangerBand())
    close = Step(
        shift(UiState(UiScreen.STAGE_LIST), UiState(UiScreen.STAGE_LIST)), (), DangerBand()
    )
    missed = ActionResult(entry, ActionStatus.UNVERIFIED)
    closed = ActionResult(close, ActionStatus.VERIFIED, outcome=close.operation.outcomes[0])
    planner = make_planner()
    memory = start()
    decision: Step | Wait | Finish = Wait()
    for acted in (missed, closed, missed, closed, missed):
        decision, memory = planner.plan(memory, sensed(Observed(UiScreen.STAGE_LIST)), acted)

    assert decision is Finish.HALTED


def test_reaching_a_goal_clears_the_strikes():
    memory = replace(start(), goals=(GRID_SHOWN, READY), strikes=2)
    settings = Observed(UiScreen.BATTLE_SETTINGS, grid_shown=True)

    _, memory = make_planner().plan(memory, sensed(settings), None)

    assert memory.strikes == 0


def test_lock_screen_is_left_through_the_ui_shift_plan():
    decision, _ = make_planner().plan(start(), sensed(Observed(UiScreen.LOCKED)), None)

    assert isinstance(decision, Step)
    assert decision.operation.precondition == UiState(UiScreen.LOCKED)
