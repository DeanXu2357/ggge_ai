from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from random import Random

import numpy as np
import pytest

from ggge_ai_2.actuator.contract import Swipe
from ggge_ai_2.agent.belief import Belief, UiBasis, UiSource
from ggge_ai_2.agent.contract import Evidence, MapReadingRecord, MapTap, Step
from ggge_ai_2.interpreter.contract import Phase
from ggge_ai_2.mapgeom.contract import (
    CellSeen,
    Faction,
    PilotState,
    Side,
    UnitRole,
    ViewPhase,
    ViewUnit,
)
from ggge_ai_2.mapgeom.stitch import StitchMapGeometry
from ggge_ai_2.mapparser.contract import (
    CellReading,
    Edge,
    MapReading,
    MechPanel,
    NameTemplate,
    PanelIcon,
    PilotPanel,
    UnitPanel,
    UnitReading,
)
from ggge_ai_2.mapparser.contract import PilotState as PanelPilotState
from ggge_ai_2.planner.map_sync import MapSyncPlanner, view_of
from ggge_ai_2.stream.contract import StillWindow
from ggge_ai_2.uisim.contract import UiScreen, UiState, UiUnitList
from ggge_ai_2.uisim.stage_sim import StageUiSim
from ggge_ai_2.uisim.stages import load_stages
from tests.ggge_ai_2.fakes.domain import FakeDomain

REAL_STAGES = Path(__file__).resolve().parents[4] / "assets" / "ui_stages" / "stages.json"
BATTLE_SIM = StageUiSim(load_stages(REAL_STAGES))
SCREEN = (2340, 1080)
STAGE = "story-1-1-hard"
OVERVIEW = UiScreen.PLAYER_PHASE_OVERVIEW


def name(seed: int) -> NameTemplate:
    return NameTemplate(np.random.default_rng(seed).integers(0, 2, (14, 60), np.uint8) * 255)


def panel(seed: int, hp: int = 5000) -> UnitPanel:
    return UnitPanel(
        MechPanel(PanelIcon.RED, name(seed), hp, 120, None, None, None),
        PilotPanel(PanelIcon.GRAY, name(seed + 1000), 30, 40, PanelPilotState.STRONG, None, None),
    )


def unit(
    pos: tuple[int, int],
    controllable: bool | None = False,
    selected: bool = False,
    enemy_selected: bool = False,
    cropped: bool = False,
) -> UnitReading:
    return UnitReading(pos, (1, 1), controllable, selected, enemy_selected, cropped)


def record(item: MapReading) -> MapReadingRecord:
    return MapReadingRecord(still(1.0), item, None, None)


def reading(
    units: tuple[UnitReading, ...] = (),
    panel_right: UnitPanel | None = None,
    panel_left: UnitPanel | None = None,
    width: int = 4,
) -> MapReading:
    cells = {(x, y): CellReading.EMPTY for x in range(width) for y in range(3)}
    for item in units:
        cells[item.pos] = CellReading.OCCUPIED
    cells[(3, 2)] = CellReading.UNREADABLE
    return MapReading(
        cells, frozenset({Edge.LEFT, Edge.TOP}), units, {}, {}, panel_right, panel_left
    )


def test_a_view_keeps_the_cells_the_borders_the_phase_and_the_turn_of_the_record():
    view = view_of(MapReadingRecord(still(1.0), reading(), Phase.PLAYER, 1), STAGE)

    assert (view.stage, view.turn, view.phase) == (STAGE, 1, ViewPhase.PLAYER)
    assert view.borders == frozenset({Side.LEFT, Side.TOP})
    assert view.cells[(0, 0)] is CellSeen.EMPTY
    assert view.cells[(3, 2)] is CellSeen.UNREADABLE
    assert len(view.cells) == 12
    assert view.tap_mark is None


def test_the_left_panel_goes_to_the_enemy_selected_unit_as_an_enemy_brief():
    enemy = panel(1)
    view = view_of(
        record(reading((unit((1, 1), enemy_selected=True), unit((2, 0))), None, enemy)), STAGE
    )

    selected, other = view.units
    assert (selected.pos, selected.faction) == ((1, 1), Faction.ENEMY)
    assert selected.brief is not None
    assert (selected.brief.mech_role, selected.brief.hp, selected.brief.en) == (
        UnitRole.ATTACK,
        5000,
        120,
    )
    assert (selected.brief.pilot_role, selected.brief.mp, selected.brief.mp_max) == (
        UnitRole.NO_ROLE,
        30,
        40,
    )
    assert selected.brief.state is PilotState.STRONG
    assert selected.brief.mech_name is not None and enemy.mech.name is not None
    assert selected.brief.mech_name.mask is enemy.mech.name.mask
    assert other == ViewUnit((2, 0), (1, 1), False, None, None)


def test_the_right_panel_goes_to_the_selected_unit_without_a_faction():
    view = view_of(
        record(reading((unit((0, 1), controllable=True, selected=True),), panel(2))), STAGE
    )

    [selected] = view.units
    assert selected.faction is None
    assert selected.brief is not None and selected.brief.hp == 5000


def test_a_view_leaves_out_a_unit_that_the_frame_cuts():
    view = view_of(record(reading((unit((2, 0)), unit((0, 1), cropped=True)))), STAGE)

    assert view.units == (ViewUnit((2, 0), (1, 1), False, None, None),)


def test_a_panel_without_its_unit_on_the_map_is_dropped():
    view = view_of(record(reading((unit((2, 0)),), None, panel(3))), STAGE)

    assert view.units == (ViewUnit((2, 0), (1, 1), False, None, None),)


def still(at: float) -> StillWindow:
    return StillWindow(at - 0.5, at, int(at))


def on(screen: UiScreen, at: float) -> Belief:
    return Belief(UiState(screen), UiBasis(UiSource.SEEN, int(at)), FakeDomain(), still(at))


def evidence(*readings: tuple[float, MapReading]) -> Evidence:
    return Evidence(tuple(MapReadingRecord(still(at), item, None, None) for at, item in readings))


class MockRandom(Random):
    def __init__(self, pick: Callable[[int, int], int]) -> None:
        super().__init__()
        self.pick = pick

    def randint(self, a: int, b: int) -> int:
        return self.pick(a, b)


def planner(start: int = 0, rng: Random | None = None) -> MapSyncPlanner:
    return MapSyncPlanner(STAGE, start, StitchMapGeometry(), BATTLE_SIM, SCREEN, rng or Random())


def board(
    width: int,
    height: int,
    units: tuple[UnitReading, ...] = (),
    borders: frozenset[Edge] = frozenset(),
    unreadable: tuple[tuple[int, int], ...] = (),
    enemy_panel: UnitPanel | None = None,
) -> MapReading:
    cells = {(x, y): CellReading.EMPTY for x in range(width) for y in range(height)}
    for item in units:
        cells[item.pos] = CellReading.OCCUPIED
    for cell in unreadable:
        cells[cell] = CellReading.UNREADABLE
    return MapReading(cells, borders, units, {}, {}, None, enemy_panel)


def swipe_of(step: Step) -> tuple[int, int]:
    assert isinstance(step.gesture, Swipe)
    (start_x, start_y), (end_x, end_y) = step.gesture.start, step.gesture.end
    return end_x - start_x, end_y - start_y


def full_map(units: tuple[UnitReading, ...], enemy_panel: UnitPanel | None) -> MapReading:
    cells = {(x, y): CellReading.EMPTY for x in range(4) for y in range(3)}
    for item in units:
        cells[item.pos] = CellReading.OCCUPIED
    borders = frozenset(Edge)
    return MapReading(cells, borders, units, {}, {}, None, enemy_panel)


def test_on_another_screen_the_planner_goes_back_to_the_overview():
    step = planner().next(on(UiScreen.SELECT_ACTION_IN_BATTLE, 1.0), evidence())

    assert step.name == "select_action_in_battle__back"


def test_on_the_overview_the_planner_closes_an_open_unit_list_first():
    belief = on(OVERVIEW, 1.0)
    belief = replace(belief, ui=replace(belief.ui, unit_list=UiUnitList.OPEN))

    step = planner().next(belief, evidence((1.0, reading((unit((1, 1)),)))))

    assert step.name == "player_phase_overview__unit_list"
    assert [expected.ui.unit_list for expected in step.expected] == [UiUnitList.CLOSED]


def test_with_the_unit_list_closed_the_planner_surveys_the_map():
    belief = on(OVERVIEW, 1.0)
    belief = replace(belief, ui=replace(belief.ui, unit_list=UiUnitList.CLOSED))

    step = planner().next(belief, evidence((1.0, reading((unit((1, 1)),)))))

    assert step.gesture == MapTap((1, 1))


def test_without_a_reading_of_this_cycle_the_planner_waits():
    step = planner().next(on(OVERVIEW, 2.0), evidence((1.0, reading((unit((1, 1)),)))))

    assert (step.name, step.gesture, step.expected) == ("map_sync_wait", None, ())


def test_the_planner_taps_a_visible_enemy_without_a_brief():
    belief = on(OVERVIEW, 1.0)

    step = planner().next(belief, evidence((1.0, reading((unit((1, 1)),)))))

    assert step.gesture == MapTap((1, 1))
    assert (step.deadline, step.expected) == (MapSyncPlanner.TAP_DEADLINE, (belief,))


def test_the_planner_does_not_tap_a_unit_that_it_controls():
    ally = unit((1, 1), controllable=True)
    step = planner().next(on(OVERVIEW, 1.0), evidence((1.0, reading((ally,)))))

    assert not isinstance(step.gesture, MapTap)


def test_the_planner_does_not_tap_a_unit_that_the_frame_cuts():
    cut = unit((1, 1), cropped=True)
    step = planner().next(on(OVERVIEW, 1.0), evidence((1.0, reading((cut,)))))

    assert not isinstance(step.gesture, MapTap)


def test_the_planner_taps_the_enemy_again_while_its_panel_has_not_shown():
    plan = planner()
    # The shape join needs 12 overlapping cells and 2 occupied cells.
    units = (unit((1, 1)), unit((2, 0), True))
    first = (1.0, reading(units, width=5))
    plan.next(on(OVERVIEW, 1.0), evidence(first))

    step = plan.next(on(OVERVIEW, 2.0), evidence(first, (2.0, reading(units, width=5))))

    assert step.gesture == MapTap((1, 1))


def test_with_every_visible_enemy_known_the_planner_swipes_toward_an_open_side():
    known = reading((unit((1, 1), enemy_selected=True),), None, panel(4))

    step = planner().next(on(OVERVIEW, 1.0), evidence((1.0, known)))

    assert isinstance(step.gesture, Swipe)
    (start_x, start_y), (end_x, end_y) = step.gesture.start, step.gesture.end
    assert end_x < start_x
    assert end_y == start_y


def test_a_survey_with_both_axes_closed_and_every_enemy_known_is_finished():
    done = full_map((unit((1, 1), enemy_selected=True), unit((2, 0), True)), panel(5))

    assert not planner().still_valid(on(OVERVIEW, 1.0), evidence((1.0, done)))


def test_a_survey_with_an_enemy_without_a_brief_is_not_finished():
    open_enemy = full_map((unit((1, 1), enemy_selected=True), unit((3, 2))), panel(6))

    assert planner().still_valid(on(OVERVIEW, 1.0), evidence((1.0, open_enemy)))


def test_a_survey_with_a_unit_of_unknown_control_is_not_finished():
    unknown = full_map((unit((1, 1), enemy_selected=True), unit((3, 2), None)), panel(7))

    assert planner().still_valid(on(OVERVIEW, 1.0), evidence((1.0, unknown)))


def test_on_a_screen_without_a_way_back_the_planner_waits():
    step = planner().next(on(UiScreen.NON_PLAYER_PHASE_BATTLE_VIEW, 1.0), evidence())

    assert step.name == "map_sync_wait"


def test_a_reading_without_cells_makes_the_planner_wait():
    step = planner().next(on(OVERVIEW, 1.0), evidence((1.0, board(0, 0))))

    assert step.name == "map_sync_wait"


def test_a_survey_without_a_reading_is_not_finished():
    assert planner().still_valid(on(OVERVIEW, 1.0), evidence())


def test_the_planner_judges_only_the_readings_after_the_survey_start():
    every_side = frozenset(Edge)
    before = board(4, 3, (unit((1, 1)), unit((0, 2))), every_side)
    after = board(4, 3, (unit((1, 1), enemy_selected=True),), every_side, enemy_panel=panel(8))
    both = evidence((1.0, before), (2.0, after))

    assert planner(start=0).still_valid(on(OVERVIEW, 2.0), both)
    assert not planner(start=1).still_valid(on(OVERVIEW, 2.0), both)


def test_the_planner_does_not_tap_the_selected_enemy_again():
    unread = UnitPanel(panel(9).mech, replace(panel(9).pilot, mp=None))
    selected = reading((unit((1, 1), enemy_selected=True),), None, unread)

    step = planner().next(on(OVERVIEW, 1.0), evidence((1.0, selected)))

    assert not isinstance(step.gesture, MapTap)


def test_the_planner_swipes_toward_a_known_enemy_out_of_view():
    side = frozenset({Edge.TOP, Edge.BOTTOM})
    allies = (unit((4, 0), True), unit((5, 3), True))
    left = board(7, 4, (unit((0, 1)), *allies), side | {Edge.LEFT})
    right = board(7, 4, (unit((1, 0), True), unit((2, 3), True)), side | {Edge.RIGHT})

    step = planner().next(on(OVERVIEW, 2.0), evidence((1.0, left), (2.0, right)))

    move_x, move_y = swipe_of(step)
    assert move_x > 0
    assert move_y == 0


def test_with_both_axes_closed_the_planner_swipes_toward_an_uncertain_cell():
    hidden = board(4, 3, (unit((0, 0), True),), frozenset(Edge), unreadable=((3, 2),))

    step = planner().next(on(OVERVIEW, 1.0), evidence((1.0, hidden)))

    move_x, move_y = swipe_of(step)
    assert move_x < 0
    assert move_y < 0


def test_a_long_swipe_stays_inside_the_swipe_area():
    wide = board(30, 3, (unit((0, 0), True), unit((1, 2), True)), frozenset({Edge.LEFT}))

    step = planner().next(on(OVERVIEW, 1.0), evidence((1.0, wide)))

    assert isinstance(step.gesture, Swipe)
    assert step.gesture.end[0] == MapSyncPlanner.SWIPE_AREA.left


@pytest.mark.parametrize("pick", [min, max])
def test_after_a_view_that_joins_nothing_the_planner_swipes_back_within_the_jitter(
    pick: Callable[[int, int], int],
):
    plan = planner(rng=MockRandom(pick))
    start = board(6, 3, (unit((0, 0), True), unit((2, 2), True)), frozenset({Edge.LEFT}))
    first = plan.next(on(OVERVIEW, 1.0), evidence((1.0, start)))
    lost = board(6, 3, (unit((5, 1), True),))

    back = plan.next(on(OVERVIEW, 2.0), evidence((1.0, start), (2.0, lost)))

    jitter = pick(-MapSyncPlanner.SWIPE_JITTER, MapSyncPlanner.SWIPE_JITTER)
    assert swipe_of(back) == (-swipe_of(first)[0] + jitter, -swipe_of(first)[1] + jitter)


def test_a_view_that_joins_nothing_before_any_swipe_makes_the_planner_wait():
    start = board(6, 3, (unit((0, 0), True), unit((2, 2), True)), frozenset({Edge.LEFT}))
    lost = board(6, 3, (unit((5, 1), True),))

    step = planner().next(on(OVERVIEW, 2.0), evidence((1.0, start), (2.0, lost)))

    assert step.name == "map_sync_wait"
