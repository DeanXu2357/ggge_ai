from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from ggge_ai_2.agent.contract import (
    ActionResult,
    ActionStatus,
    CellReads,
    Finish,
    Sensed,
    Step,
    Wait,
)
from ggge_ai_2.mapgeom.contract import (
    Alignment,
    BoardEdge,
    CellContent,
    KnownMap,
    LocalBoard,
    MapGeometry,
    WorldCell,
)
from ggge_ai_2.mapparser.contract import CellReading, MapReading
from ggge_ai_2.planner.mapsync.contract import Explored, MapSyncPlan, Probe
from ggge_ai_2.planner.uishift.contract import UiShiftPlan
from ggge_ai_2.stream.contract import StillWindow
from ggge_ai_2.uisim.contract import (
    Observed,
    UiAuto,
    UiMapMode,
    UiOverlay,
    UiScreen,
    UiSim,
    UiState,
)

READY = UiState(UiScreen.BATTLE_MAP, map_mode=UiMapMode.HUB, auto=UiAuto.OFF, grid_shown=True)
GRID_SHOWN = UiState(UiScreen.BATTLE_SETTINGS, grid_shown=True)
STAGE_INFO = UiState(UiScreen.STAGE_INFO)
LEFT = UiState(UiScreen.STAGE_LIST)
CLOSABLE = frozenset({UiOverlay.DIALOG, UiOverlay.CARD})


class UiSource(StrEnum):
    ASSUMED = "assumed"
    SEEN = "seen"
    PREDICTED = "predicted"
    LOST = "lost"


@dataclass(frozen=True)
class UiBasis:
    source: UiSource
    frame_seq: int | None = None
    outcome: str | None = None


@dataclass(frozen=True)
class Belief:
    ui: UiState
    ui_basis: UiBasis
    camera: Alignment | None
    known_map: KnownMap
    as_of: StillWindow | None

    def revise_when_acted(self, acted: ActionResult, uisim: UiSim) -> Belief:
        if acted.outcome is None:
            return self
        basis = UiBasis(UiSource.PREDICTED, outcome=acted.outcome.name)
        return replace(self, ui=uisim.advance(self.ui, acted.outcome), ui_basis=basis)

    def revise_when_sensed(self, sensed: Sensed, uisim: UiSim, mapgeom: MapGeometry) -> Belief:
        ui, basis = self._read_ui(sensed.still.frame_seq, sensed.observed, uisim)
        camera, known_map = self.camera, self.known_map
        board = _map_reading_to_local_board(sensed.map)
        if board is not None:
            alignment = mapgeom.align(board, known_map, camera)
            if alignment is not None:
                camera, known_map = alignment, mapgeom.merge(known_map, board, alignment)
        return replace(
            self, ui=ui, ui_basis=basis, camera=camera, known_map=known_map, as_of=sensed.still
        )

    def _read_ui(
        self, frame_seq: int, observed: Observed | None, uisim: UiSim
    ) -> tuple[UiState, UiBasis]:
        if observed is not None:
            return uisim.sync(self.ui, observed), UiBasis(UiSource.SEEN, frame_seq=frame_seq)
        if self.ui_basis.source is UiSource.LOST:
            return self.ui, self.ui_basis
        return self.ui, UiBasis(UiSource.LOST, frame_seq=frame_seq)


@dataclass(frozen=True)
class Memory:
    belief: Belief
    goals: tuple[UiState, ...] = ()
    explored: bool = False
    strikes: int = 0


type Decision = tuple[Step | Wait | Finish, Memory]


@dataclass(frozen=True)
class RulePlanner:
    uisim: UiSim
    mapgeom: MapGeometry
    uishift: UiShiftPlan
    mapsync: MapSyncPlan
    recorded: KnownMap | None = None
    max_strikes: int = 3

    def plan(self, state: Memory, sensed: Sensed, acted: ActionResult | None) -> Decision:
        belief = state.belief
        if acted is not None:
            belief = belief.revise_when_acted(acted, self.uisim)
        belief = belief.revise_when_sensed(sensed, self.uisim, self.mapgeom)
        strikes = state.strikes
        if acted is not None and acted.status is not ActionStatus.VERIFIED:
            strikes += 1
        if len(belief.known_map.cells) > len(state.belief.known_map.cells):
            strikes = 0
        return self._decide(replace(state, belief=belief, strikes=strikes), acted)

    def _decide(self, memory: Memory, acted: ActionResult | None) -> Decision:
        belief = memory.belief
        ui = belief.ui
        if belief.ui_basis.source is UiSource.LOST:
            return Finish.HALTED, memory
        if acted is not None and acted.status is ActionStatus.BLOCKED:
            return Finish.HALTED, memory
        if memory.strikes >= self.max_strikes:
            return Finish.HALTED, memory
        if ui.overlays & CLOSABLE:
            return self._shift(memory, replace(ui, overlays=ui.overlays - CLOSABLE))

        goals = memory.goals
        while goals and goals[0] == ui:
            goals = goals[1:]
        if goals != memory.goals:
            memory = replace(memory, goals=goals, strikes=0)
        if goals:
            return self._shift(memory, goals[0])
        if memory.explored:
            return Finish.DONE, memory
        if ui.screen is not UiScreen.BATTLE_MAP:
            return self._shift(memory, READY)
        if ui.map_mode is not UiMapMode.HUB:
            return self._shift(memory, replace(ui, map_mode=UiMapMode.HUB))
        if self.recorded is not None:
            return Finish.HALTED, memory

        prerequisites = _prerequisites(ui)
        if prerequisites:
            return self._shift(replace(memory, goals=prerequisites), prerequisites[0])
        if belief.camera is None:
            return Wait(), memory
        match self.mapsync.next(belief.known_map, belief.camera):
            case Explored():
                return self._shift(replace(memory, goals=(LEFT,), explored=True), LEFT)
            case Probe(cell):
                return self._probe(memory, belief.camera, cell)
            case None:
                return Finish.HALTED, memory

    def _shift(self, memory: Memory, goal: UiState) -> Decision:
        op = self.uishift.next(memory.belief.ui, goal)
        if op is None:
            return Finish.HALTED, memory
        return Step(op, (), self.uisim.danger_band(op.precondition)), memory

    def _probe(self, memory: Memory, camera: Alignment, cell: WorldCell) -> Decision:
        belief = memory.belief
        op = self.uishift.tap_map(belief.ui)
        if op is None:
            return Finish.HALTED, memory
        view = camera.to_view(cell)
        seen = belief.known_map.cells.get(cell)
        premise = () if seen is None else (CellReads(view, _cell_content_to_reading(seen)),)
        return Step(op, premise, self.uisim.danger_band(op.precondition), target=view), memory


def _prerequisites(ui: UiState) -> tuple[UiState, ...]:
    if ui.auto in (UiAuto.ON, UiAuto.ACTIVE):
        return (replace(ui, auto=UiAuto.OFF), GRID_SHOWN, STAGE_INFO, READY)
    if ui.grid_shown is not True:
        return (GRID_SHOWN, READY)
    return ()


def _map_reading_to_local_board(reading: MapReading | None) -> LocalBoard | None:
    if reading is None:
        return None
    return LocalBoard(
        {cell: CellContent(seen.value) for cell, seen in reading.cells.items()},
        frozenset(BoardEdge(edge.value) for edge in reading.borders),
    )


def _cell_content_to_reading(content: CellContent) -> CellReading:
    return CellReading(content.value)
