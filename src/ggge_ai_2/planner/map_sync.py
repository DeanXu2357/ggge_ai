from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, fields
from random import Random
from typing import ClassVar

from ggge_ai_2.actuator.contract import Rect, ScreenPoint, Swipe
from ggge_ai_2.agent.belief import Belief
from ggge_ai_2.agent.contract import Evidence, MapTap, Step
from ggge_ai_2.agent.trace import traced
from ggge_ai_2.agent.ui_steps import danger_rects, first_move, operation_step
from ggge_ai_2.mapgeom.contract import (
    CellSeen,
    Faction,
    MapCell,
    MapGeometry,
    MapJudgment,
    NameMask,
    PilotState,
    Side,
    UnitBrief,
    UnitRole,
    View,
    ViewPhase,
    ViewUnit,
)
from ggge_ai_2.mapparser.contract import MapReading, NameTemplate, PanelIcon, UnitPanel
from ggge_ai_2.uisim.contract import (
    DangerBand,
    Observed,
    Operation,
    Outcome,
    UiScreen,
    UiSim,
    UiState,
)

OVERVIEW = UiScreen.PLAYER_PHASE_OVERVIEW
WAIT = Step("map_sync_wait", None, (), 0.0, ())
Move = tuple[int, int]

ROLES = {
    PanelIcon.RED: UnitRole.ATTACK,
    PanelIcon.BLUE: UnitRole.ENDURANCE,
    PanelIcon.YELLOW: UnitRole.SUPPORT,
    PanelIcon.GRAY: UnitRole.NO_ROLE,
}


@dataclass
class MapSyncPlanner:
    # The deadline of 'player_phase_overview__map_enemy_unit' in 'stages.json'. The
    # transition has no rect, so the uisim does not offer it.
    TAP_DEADLINE: ClassVar[float] = 4.6
    # These values are hypotheses. They apply only to the test phone R5CRC37JBYJ
    # (2340x1080). The cell size comes from frame rec20261014-639.
    CELL_PIXELS: ClassVar[int] = 125
    SWIPE_CENTRE: ClassVar[ScreenPoint] = (1170, 450)
    SWIPE_AREA: ClassVar[Rect] = Rect(150, 150, 2190, 720)
    SWIPE_DURATION: ClassVar[float] = 1.0
    SWIPE_DEADLINE: ClassVar[float] = 1.5
    # The jitter moves a swipe back off the exact reverse of the last swipe. Then the
    # next swipe starts from a new view and does not repeat a view that joins nothing.
    SWIPE_JITTER: ClassVar[int] = 125

    stage: str
    # The number of map readings in the evidence before the survey.
    start: int
    geometry: MapGeometry
    uisim: UiSim
    screen: tuple[int, int]
    rng: Random
    _last_drag: tuple[int, int] | None = field(default=None, init=False)
    _judged: tuple[int, MapJudgment | None] | None = field(default=None, init=False)

    def still_valid(self, belief: Belief, evidence: Evidence) -> bool:
        return not self.finished(evidence)

    def finished(self, evidence: Evidence) -> bool:
        return _finished(self.judgment(evidence))

    def judgment(self, evidence: Evidence) -> MapJudgment | None:
        records = evidence.map_readings[self.start :]
        # The evidence only grows, so its length names it. The loop asks 'still_valid' and
        # 'next' on one evidence in each cycle, and a judgment joins every view again.
        if self._judged is None or self._judged[0] != len(records):
            views = [view_of(record.reading, self.stage) for record in records]
            self._judged = (len(records), self.geometry.judge(views))
        return self._judged[1]

    @traced
    def next(self, belief: Belief, evidence: Evidence) -> Step:
        assert belief.as_of is not None, "the main loop plans only on a sensed belief"
        if belief.ui.screen is not OVERVIEW:
            move = first_move(_WayBack(self.uisim), belief.ui, OVERVIEW)
            if move is None:
                return WAIT
            return operation_step(move[0], belief, self.uisim, self.screen)
        records = evidence.map_readings[self.start :]
        if not records or records[-1].still != belief.as_of:
            return WAIT
        judgment = self.judgment(evidence)
        if judgment is None:
            return WAIT
        if judgment.current is None:
            if self._last_drag is None:
                return WAIT
            jitter = self.SWIPE_JITTER
            back = (
                -self._last_drag[0] + self.rng.randint(-jitter, jitter),
                -self._last_drag[1] + self.rng.randint(-jitter, jitter),
            )
            return self._swipe(belief, back)
        latest = records[-1].reading
        target = _tap_target(judgment, latest, _shift(judgment.current, latest.cells))
        if target is not None:
            band = danger_rects(self.uisim, belief, self.screen)
            return Step("map_sync_tap_enemy", MapTap(target), band, self.TAP_DEADLINE, (belief,))
        move = _move(judgment, judgment.current)
        if move is None:
            return WAIT
        return self._swipe(belief, (-move[0] * self.CELL_PIXELS, -move[1] * self.CELL_PIXELS))

    def _swipe(self, belief: Belief, drag: tuple[int, int]) -> Step:
        area = self.SWIPE_AREA
        start_x, start_y = self.SWIPE_CENTRE
        end = (
            min(max(start_x + drag[0], area.left), area.right),
            min(max(start_y + drag[1], area.top), area.bottom),
        )
        self._last_drag = (end[0] - start_x, end[1] - start_y)
        swipe = Swipe(self.SWIPE_CENTRE, end, self.SWIPE_DURATION)
        band = danger_rects(self.uisim, belief, self.screen)
        return Step("map_sync_swipe", swipe, band, self.SWIPE_DEADLINE, (belief,))


# '待機' also leads to the overview, but it ends the action of the unit.
@dataclass(frozen=True)
class _WayBack:
    uisim: UiSim

    def successors(self, state: UiState) -> Sequence[Operation]:
        return [
            operation
            for operation in self.uisim.successors(state)
            if operation.name.endswith(("__back", "__close"))
        ]

    def advance(self, state: UiState, outcome: Outcome) -> UiState:
        return self.uisim.advance(state, outcome)

    def sync(self, state: UiState, observed: Observed) -> UiState:
        return self.uisim.sync(state, observed)

    def danger_band(self, state: UiState) -> DangerBand:
        return self.uisim.danger_band(state)


def _finished(judgment: MapJudgment | None) -> bool:
    if judgment is None or judgment.uncertain:
        return False
    if judgment.columns.size() is None or judgment.rows.size() is None:
        return False
    return all(
        unit.controllable is not None and (unit.controllable or _complete(unit.brief))
        for unit in judgment.units.values()
    )


def _complete(brief: UnitBrief | None) -> bool:
    return brief is not None and all(
        getattr(brief, item.name) is not None for item in fields(brief)
    )


def _shift(current: frozenset[MapCell], view_cells: Iterable[tuple[int, int]]) -> Move:
    cells = list(view_cells)
    return (
        min(x for x, _ in current) - min(x for x, _ in cells),
        min(y for _, y in current) - min(y for _, y in cells),
    )


def _tap_target(judgment: MapJudgment, latest: MapReading, shift: Move) -> tuple[int, int] | None:
    for unit in latest.units:
        if unit.cropped or unit.controllable is not False or unit.enemy_selected:
            continue
        unit_id = judgment.unit_cells.get((unit.pos[0] + shift[0], unit.pos[1] + shift[1]))
        if unit_id is not None and not _complete(judgment.units[unit_id].brief):
            return unit.pos
    return None


def _move(judgment: MapJudgment, current: frozenset[MapCell]) -> Move | None:
    left, right = min(x for x, _ in current), max(x for x, _ in current)
    top, bottom = min(y for _, y in current), max(y for _, y in current)
    centre = ((left + right) // 2, (top + bottom) // 2)
    reach = (max(1, (right - left) // 2), max(1, (bottom - top) // 2))
    for target in _targets(judgment, centre):
        move = (
            max(-reach[0], min(reach[0], target[0] - centre[0])),
            max(-reach[1], min(reach[1], target[1] - centre[1])),
        )
        if move != (0, 0):
            return move
    return None


def _targets(judgment: MapJudgment, centre: MapCell) -> list[MapCell]:
    anchors: dict[int, MapCell] = {}
    for cell, unit_id in judgment.unit_cells.items():
        anchors[unit_id] = min(anchors.get(unit_id, cell), cell)
    unknown_briefs = [
        anchors[unit_id]
        for unit_id, unit in judgment.units.items()
        if unit.controllable is False and not _complete(unit.brief)
    ]
    unknown_control = [
        anchors[unit_id] for unit_id, unit in judgment.units.items() if unit.controllable is None
    ]
    columns, rows = judgment.columns, judgment.rows
    open_sides = [
        target
        for closed, target in (
            (columns.start_closed, (-1, centre[1])),
            (columns.end_closed, (columns.length, centre[1])),
            (rows.start_closed, (centre[0], -1)),
            (rows.end_closed, (centre[0], rows.length)),
        )
        if not closed
    ]
    uncertain = sorted(
        judgment.uncertain,
        key=lambda cell: abs(cell[0] - centre[0]) + abs(cell[1] - centre[1]),
    )
    return unknown_briefs + unknown_control + open_sides + uncertain


def view_of(reading: MapReading, stage: str) -> View:
    units: list[ViewUnit] = []
    # mapgeom joins whole units only. A cut unit shows whole in a view from another place.
    for unit in (unit for unit in reading.units if not unit.cropped):
        faction, panel = None, None
        if unit.enemy_selected:
            faction, panel = Faction.ENEMY, reading.enemy_panel
        elif unit.selected:
            panel = reading.panel
        units.append(
            ViewUnit(
                unit.pos,
                unit.size,
                unit.controllable,
                faction,
                None if panel is None else _brief(panel),
            )
        )
    return View(
        stage=stage,
        turn=reading.turn,
        phase=None if reading.phase is None else ViewPhase(reading.phase.value),
        cells={cell: CellSeen(seen.value) for cell, seen in reading.cells.items()},
        borders=frozenset(Side(edge.value) for edge in reading.borders),
        units=tuple(units),
        tap_mark=None,
    )


def _brief(panel: UnitPanel) -> UnitBrief:
    mech, pilot = panel.mech, panel.pilot
    return UnitBrief(
        mech_role=_role(mech.icon),
        mech_name=_name(mech.name),
        hp=mech.hp,
        en=mech.en,
        pilot_role=_role(pilot.icon),
        pilot_name=_name(pilot.name),
        mp=pilot.mp,
        mp_max=pilot.mp_max,
        state=None if pilot.state is None else PilotState(pilot.state.value),
    )


def _role(icon: PanelIcon | None) -> UnitRole | None:
    return None if icon is None else ROLES[icon]


def _name(template: NameTemplate | None) -> NameMask | None:
    return None if template is None else NameMask(template.mask)
