"""盤面全覽的符號建模：前置條件、規劃排序、恢復式微步驟、覆蓋簿記與衰效。"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import pytest

from ggge_ai.contracts import Ending, HiddenPolicy, Objective, StageOrder
from ggge_ai.runtime.board import BoardScan
from ggge_ai.runtime.device import LiveExecutor
from ggge_ai.runtime.journal import Journal
from ggge_ai.runtime.perceive import Observation
from ggge_ai.sandbox.advise import Guarantee, Pricing
from ggge_ai.runtime import screens
from ggge_ai.stage.actions import Attack, CollapseRoster, ShowGrid, SurveyBoard, candidates
from ggge_ai.stage.goals import Annihilation
from ggge_ai.stage.loop import StageLoop, TickOutcome
from ggge_ai.stage.planner import PlannerConfig, plan
from ggge_ai.stage.run import JOURNAL_NAME
from ggge_ai.stage.state import Phase, StageState, next_player_phase
from ggge_ai.stage.survey import (
    MERGE_STEP,
    ROSTER_ALREADY,
    ROSTER_TAPPED,
    ROSTER_UNREADABLE,
    ZOOM_STEP,
    CoverageLedger,
    SurveyPerceiver,
    survey_drivers,
)
from tests.fixtures.frames import load
from tests.fixtures.stage_offline import MockAdvisor, ScriptedPerceiver, battle, frame

SERIES = Path(__file__).resolve().parent / "fixtures" / "vision" / "map_scan" / "ex2if_20260719"
FREE = Pricing(1.0)
ROSTER_EXPANDED_FRAME = "forecast/our_turn_unit_list_20260719"
ROSTER_COLLAPSED_FRAME = "forecast/our_turn_list_collapsed_20260719"
ROSTER_COVERED_FRAME = "forecast/unit_detail_combined_20260719"


@functools.cache
def map_frame() -> np.ndarray:
    image = cv2.imread(str(SERIES / "03_pt3_pan_up.png"))
    assert image is not None
    return image


@dataclass
class FakeActuator:
    taps: list[tuple[int, int, str]] = field(default_factory=list)
    swipes: list[tuple[int, int, int, int, float]] = field(default_factory=list)

    def tap(self, x: int, y: int, intent: str = "") -> None:
        self.taps.append((x, y, intent))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_s: float) -> None:
        self.swipes.append((x1, y1, x2, y2, duration_s))

    def key(self, keycode: str) -> None:
        raise AssertionError("掃描不用按鍵")


@dataclass
class Camera:
    """腳本化鏡頭：每次平移把畫面捲一段，或（到邊時）原地不動。"""

    frames: list[np.ndarray]
    index: int = 0

    def capture(self) -> np.ndarray:
        return self.frames[min(self.index, len(self.frames) - 1)]

    def advance(self) -> None:
        self.index += 1


def rolled(steps: int) -> np.ndarray:
    return np.roll(map_frame(), -250 * steps, axis=1)


def _survey_then_kill(current: StageState, action) -> Pricing | None:
    """情報不全＝行為：盤面沒同步就不替戰鬥背書，計畫自己長出掃描。"""
    if isinstance(action, Attack):
        return Pricing(1.0, Guarantee.KILL) if current.board_synced else None
    if isinstance(action, ShowGrid | CollapseRoster | SurveyBoard):
        return Pricing(1.0)
    return None


def test_the_survey_needs_the_grid_first():
    """grid_on 是符號前置條件：沒格線就不可掃，也沒有降級版可以掃。"""
    dark = battle(allies=["a1"], enemies=["e1"], grid_on=False, board_synced=False)

    assert not SurveyBoard().applicable(dark)
    assert ShowGrid().applicable(dark)


def test_the_survey_needs_the_roster_strip_collapsed_too():
    """展開的卡條蓋住掃描帶下緣（一路到 y1020）：同 grid_on，前置條件是符號的。"""
    open_strip = battle(allies=["a1"], enemies=["e1"], roster_collapsed=False, board_synced=False)

    assert not SurveyBoard().applicable(open_strip)
    assert CollapseRoster().applicable(open_strip)

    collapsed = CollapseRoster().apply(open_strip, FREE)

    assert collapsed.roster_collapsed
    assert SurveyBoard().applicable(collapsed)
    assert CollapseRoster().progressed(collapsed, FREE)
    assert not CollapseRoster().applicable(collapsed)


def test_collapsing_the_roster_is_a_candidate_only_while_the_strip_is_open():
    open_strip = battle(allies=["a1"], enemies=["e1"], roster_collapsed=False, board_synced=False)
    collapsed = battle(allies=["a1"], enemies=["e1"], board_synced=False)

    assert "collapse_roster" in [action.label for action in candidates(open_strip)]
    assert "collapse_roster" not in [action.label for action in candidates(collapsed)]


def test_the_planner_collapses_the_roster_before_the_survey():
    state = battle(
        allies=["a1"],
        enemies=["e1"],
        grid_on=False,
        roster_collapsed=False,
        board_synced=False,
        known=["a1", "e1"],
    )

    labels = [
        step.action.label
        for step in plan(
            state, Annihilation(), MockAdvisor(_survey_then_kill), PlannerConfig()
        ).steps
    ]

    assert labels.index("collapse_roster") < labels.index("survey_board")
    assert labels.index("show_grid") < labels.index("survey_board")


def test_a_turn_boundary_makes_the_collapse_stale_again():
    """換回合重算可行動單位、卡條重繪：搜尋側取保守的那一邊（還要再收一次）。"""
    collapsed = battle(allies=["a1"], enemies=["e1"], actionable=[])

    assert not next_player_phase(collapsed).roster_collapsed


def test_the_driver_reads_the_strip_before_touching_the_toggle():
    actuator = FakeActuator()
    driver, _ = survey_drivers(
        lambda: load(ROSTER_COLLAPSED_FRAME), actuator, sleep=lambda _: None
    )

    step = driver.collapse_roster(CollapseRoster(), Observation(screen="battle_map"))

    assert step == ROSTER_ALREADY
    assert actuator.taps == []


def test_the_driver_taps_the_toggle_when_the_strip_is_open():
    actuator = FakeActuator()
    driver, _ = survey_drivers(lambda: load(ROSTER_EXPANDED_FRAME), actuator, sleep=lambda _: None)

    step = driver.collapse_roster(CollapseRoster(), Observation(screen="battle_map"))

    assert step == ROSTER_TAPPED
    assert [(x, y) for x, y, _ in actuator.taps] == [screens.ROSTER_TOGGLE_TAP]


def test_an_unreadable_strip_is_never_tapped_blind():
    """彈窗蓋住條帶＝讀不出來，不是收好了。盲點一下會把收好的卡條又展開。"""
    actuator = FakeActuator()
    driver, _ = survey_drivers(lambda: load(ROSTER_COVERED_FRAME), actuator, sleep=lambda _: None)

    step = driver.collapse_roster(CollapseRoster(), Observation(screen="battle_map"))

    assert step == ROSTER_UNREADABLE
    assert actuator.taps == []


def test_the_journal_records_which_micro_step_the_driver_did(tmp_path):
    """驅動型行動的自述要進流水帳：不然事後只看得到「做過一次掃描」，看不出那一 tick
    是縮放、平移還是合併，也看不出收卡條是點了還是本來就收好。"""
    journal = Journal(tmp_path / JOURNAL_NAME)
    driver, ledger = survey_drivers(
        lambda: load(ROSTER_COLLAPSED_FRAME), FakeActuator(), sleep=lambda _: None
    )
    executor = LiveExecutor(
        device=FakeActuator(), drivers=driver.drivers(), journal=journal, sleep=lambda _: None
    )
    ledger.zoomed = True

    executor.perform(CollapseRoster(), Observation(screen="battle_map"))

    recorded = [line for line in journal.entries() if line["kind"] == "perform"]
    assert [(line["label"], line["step"]) for line in recorded] == [
        ("collapse_roster", ROSTER_ALREADY)
    ]


def test_the_perceiver_takes_the_strip_state_from_the_frame_evidence():
    """感知權威：逐幀觀測覆寫符號狀態，讀不出來一律折成「沒收起」。"""
    seen = Observation(
        screen="battle_map",
        state=battle(allies=["a1"], enemies=["e1"], roster_collapsed=False),
        evidence={"roster_strip": screens.ROSTER_COLLAPSED},
    )
    covered = Observation(
        screen="battle_map",
        state=battle(allies=["a1"], enemies=["e1"]),
        evidence={"roster_strip": None},
    )

    assert SurveyPerceiver(ScriptedPerceiver([seen]), CoverageLedger()).look().state.roster_collapsed
    assert (
        not SurveyPerceiver(ScriptedPerceiver([covered]), CoverageLedger())
        .look()
        .state.roster_collapsed
    )


def test_showing_the_grid_supplies_the_precondition():
    dark = battle(allies=["a1"], enemies=["e1"], grid_on=False, board_synced=False)

    lit = ShowGrid().apply(dark, FREE)

    assert lit.grid_on
    assert SurveyBoard().applicable(lit)
    assert ShowGrid().progressed(lit, FREE)
    assert not ShowGrid().applicable(lit)


def test_the_survey_is_done_when_the_board_is_synced():
    lit = battle(allies=["a1"], enemies=["e1"], board_synced=False)

    after = SurveyBoard().apply(lit, FREE)

    assert after.board_synced
    assert SurveyBoard().progressed(after, FREE)
    assert not SurveyBoard().applicable(after)


def test_partial_coverage_is_not_completion():
    """swept 是恢復點不是完成條件：掃了一半仍然沒完成。"""
    halfway = battle(
        allies=["a1"], enemies=["e1"], board_synced=False, swept=["west", "north"]
    )

    assert not SurveyBoard().progressed(halfway, FREE)
    assert SurveyBoard().applicable(halfway)


def test_both_board_actions_show_up_as_candidates_only_when_applicable():
    dark = battle(allies=["a1"], enemies=["e1"], grid_on=False, board_synced=False)
    lit = battle(allies=["a1"], enemies=["e1"], board_synced=False)
    done = battle(allies=["a1"], enemies=["e1"])

    assert "show_grid" in [action.label for action in candidates(dark)]
    assert "survey_board" not in [action.label for action in candidates(dark)]
    assert "survey_board" in [action.label for action in candidates(lit)]
    assert "show_grid" not in [action.label for action in candidates(lit)]
    assert not {"show_grid", "survey_board"} & {action.label for action in candidates(done)}


def test_the_planner_orders_show_grid_before_the_survey():
    """規劃器自然排序：Advisor 不替沒同步盤面的攻擊背書，計畫就自己長出
    開格線→掃描→攻擊。"""
    state = battle(
        allies=["a1"], enemies=["e1"], grid_on=False, board_synced=False, known=["a1", "e1"]
    )

    result = plan(state, Annihilation(), MockAdvisor(_survey_then_kill), PlannerConfig())

    assert [step.action.label for step in result.steps] == [
        "show_grid",
        "survey_board",
        "attack:a1->e1",
    ]


def test_a_turn_boundary_expires_the_board_sync():
    """敵方回合過完，敵人都動過，站位全部作廢。格線不受影響。"""
    synced = battle(allies=["a1"], enemies=["e1"], actionable=[], swept=["west"])

    after = next_player_phase(synced)

    assert after.grid_on
    assert not after.board_synced
    assert after.swept == frozenset()


def test_the_ledger_walks_zoom_then_every_direction_then_the_merge():
    ledger = CoverageLedger(itinerary=("west", "east"))

    assert ledger.next_step() == ZOOM_STEP
    ledger.zoomed = True
    assert ledger.next_step() == "west"
    ledger.edge_reached("west")
    assert ledger.next_step() == "east"
    ledger.edge_reached("east")
    assert ledger.next_step() == MERGE_STEP


def test_a_direction_that_never_reaches_an_edge_stops_at_its_leg_budget():
    """誠實停在有限覆蓋，而不是把整批 tick 燒在一個方向上。"""
    ledger = CoverageLedger(itinerary=("west",), legs_per_direction=2)
    ledger.zoomed = True

    ledger.leg_done("west")
    assert "west" not in ledger.swept
    ledger.leg_done("west")

    assert ledger.swept == {"west"}


def test_the_driver_does_exactly_one_micro_step_per_call():
    """一 tick 一個微步驟：反射才插得進來。"""
    camera = Camera([map_frame(), rolled(1), rolled(2), rolled(2)])
    actuator = FakeActuator()
    driver, ledger = survey_drivers(
        camera.capture, actuator, itinerary=("west",), sleep=lambda _: None
    )

    def pan(*args, **kwargs):
        camera.advance()
        actuator.swipes.append(args)

    driver._pan = lambda direction, origin: pan(direction, origin)

    assert driver.survey_board(SurveyBoard(), Observation(screen="battle_map")) == ZOOM_STEP
    assert ledger.zoomed
    assert actuator.swipes == []

    assert driver.survey_board(SurveyBoard(), Observation(screen="battle_map")) == "west"
    assert len(actuator.swipes) == 1


def test_the_zoom_micro_step_runs_the_injected_zoom_out():
    """縮放實作住 runtime/zoom.py（要 uiautomator 注入通道），掃描只認這個接縫。"""
    camera = Camera([map_frame()])
    zooms: list[int] = []
    driver, _ = survey_drivers(
        camera.capture,
        FakeActuator(),
        itinerary=("west",),
        zoom_out=lambda: zooms.append(1),
        sleep=lambda _: None,
    )

    assert driver.survey_board(SurveyBoard(), Observation(screen="battle_map")) == ZOOM_STEP
    assert zooms == [1]

    driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))

    assert zooms == [1]  # 只在縮放那一個微步驟，之後的平移不再碰鏡頭


def test_the_survey_carries_on_without_a_zoom_backend():
    """縮放是最佳化不是前提：接不上後端照樣掃得完，只是腿數變多。"""
    camera = Camera([map_frame()])
    driver, ledger = survey_drivers(
        camera.capture, FakeActuator(), itinerary=("west",), sleep=lambda _: None
    )

    assert driver.survey_board(SurveyBoard(), Observation(screen="battle_map")) == ZOOM_STEP
    assert ledger.zoomed
    assert driver.survey_board(SurveyBoard(), Observation(screen="battle_map")) == "west"


def test_the_driver_marks_a_direction_swept_when_the_view_stops_moving():
    camera = Camera([map_frame()])
    driver, ledger = survey_drivers(
        camera.capture, FakeActuator(), itinerary=("west",), sleep=lambda _: None
    )
    ledger.zoomed = True

    step = driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))

    assert step == "west"
    assert ledger.swept == {"west"}
    assert ledger.next_step() == MERGE_STEP


def test_the_merge_step_writes_the_scan_back_and_completes_the_survey():
    camera = Camera([map_frame()])
    driver, ledger = survey_drivers(
        camera.capture, FakeActuator(), itinerary=("west",), sleep=lambda _: None
    )
    ledger.zoomed = True

    driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))
    step = driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))

    assert step == MERGE_STEP
    assert ledger.synced
    assert ledger.cells()


def test_the_driver_resumes_from_the_ledger_not_from_its_own_variables():
    """換一個執行器實例也接得下去——恢復點在簿記，不在執行器內部。"""
    ledger = CoverageLedger(itinerary=("west", "east"))
    ledger.zoomed = True
    ledger.edge_reached("west")
    camera = Camera([map_frame()])

    driver, _ = survey_drivers(
        camera.capture, FakeActuator(), ledger=ledger, sleep=lambda _: None
    )

    assert driver.survey_board(SurveyBoard(), Observation(screen="battle_map")) == "east"


def test_an_expired_ledger_throws_away_the_old_world_frame():
    """衰效不只清覆蓋：上一輪的累積位移與目擊都作廢，否則新目擊會疊在舊
    座標系上。"""
    camera = Camera([map_frame()])
    driver, ledger = survey_drivers(
        camera.capture, FakeActuator(), itinerary=("west",), sleep=lambda _: None
    )
    ledger.zoomed = True
    driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))
    driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))
    stale = driver.cursor

    ledger.expire()
    driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))

    assert driver.cursor is not stale
    assert driver.cursor.scan.frames == 1


def test_the_perceiver_folds_the_coverage_ledger_into_the_symbolic_state():
    ledger = CoverageLedger()
    ledger.edge_reached("west")
    seen = frame(battle(allies=["a1"], enemies=["e1"], board_synced=False, grid_on=False))
    perceiver = SurveyPerceiver(ScriptedPerceiver([seen]), ledger)

    state = perceiver.look().state

    assert state.swept == {"west"}
    assert not state.board_synced


def test_the_perceiver_takes_grid_on_from_the_frame_evidence():
    seen = Observation(
        screen="battle_map",
        state=battle(allies=["a1"], enemies=["e1"], grid_on=False),
        evidence={"grid_on": True},
    )
    perceiver = SurveyPerceiver(ScriptedPerceiver([seen]), CoverageLedger())

    assert perceiver.look().state.grid_on is True


def test_an_enemy_phase_expires_the_ledger_so_the_next_turn_rescans():
    ledger = CoverageLedger()
    ledger.edge_reached("west")
    ledger.record(BoardScan())
    enemy_turn = frame(
        battle(allies=["a1"], enemies=["e1"], actionable=[], phase=Phase.ENEMY)
    )
    perceiver = SurveyPerceiver(ScriptedPerceiver([enemy_turn]), ledger)

    state = perceiver.look().state

    assert not ledger.synced
    assert ledger.swept == set()
    assert not state.board_synced


def test_a_screen_with_no_symbolic_reading_passes_straight_through():
    perceiver = SurveyPerceiver(
        ScriptedPerceiver([Observation(screen="cutscene")]), CoverageLedger()
    )

    assert perceiver.look().state is None


def test_the_survey_action_stays_at_the_queue_head_across_ticks(tmp_path):
    """佇列頭跨 tick 重入：畫面還沒說掃完，計畫就不彈。"""
    unsynced = battle(allies=["a1"], enemies=["e1"], board_synced=False)
    order = StageOrder(
        stage="S01",
        objectives=frozenset({Objective.CLEAR}),
        hidden_policy=HiddenPolicy.DECLINE,
        max_ticks=5,
    )

    performed: list[str] = []
    executor = LiveExecutor(
        device=FakeActuator(),
        drivers={SurveyBoard: lambda action, observation: performed.append(action.label)},
        sleep=lambda _: None,
    )
    loop = StageLoop(
        order,
        perceiver=ScriptedPerceiver([frame(unsynced), frame(unsynced), frame(unsynced)]),
        executor=executor,
        advisor=MockAdvisor(_survey_then_kill),
        victory=Annihilation(),
        journal=Journal(tmp_path / JOURNAL_NAME),
    )

    outcomes = [loop.tick().outcome for _ in range(3)]

    assert outcomes == [TickOutcome.ACTED] * 3
    assert performed == ["survey_board"] * 3
    assert [step.action.label for step in loop.queue][0] == "survey_board"


def test_a_reflex_can_interrupt_the_survey_and_it_carries_on(tmp_path):
    from ggge_ai.runtime import screens
    from ggge_ai.runtime.reflexes import UNIT_DETAIL_FIX, PopupReflex

    unsynced = battle(allies=["a1"], enemies=["e1"], board_synced=False)
    order = StageOrder(
        stage="S01",
        objectives=frozenset({Objective.CLEAR}),
        hidden_policy=HiddenPolicy.DECLINE,
        max_ticks=5,
    )
    frames = [
        frame(unsynced),
        Observation(screen=screens.UNIT_DETAIL),
        frame(unsynced),
        Observation(screen="battle_result", terminal=Ending.VICTORY),
    ]
    performed: list[str] = []
    executor = LiveExecutor(
        device=FakeActuator(),
        drivers={SurveyBoard: lambda action, observation: performed.append("survey")},
        sleep=lambda _: None,
    )
    loop = StageLoop(
        order,
        perceiver=ScriptedPerceiver(frames),
        executor=executor,
        advisor=MockAdvisor(_survey_then_kill),
        victory=Annihilation(),
        journal=Journal(tmp_path / JOURNAL_NAME),
        reflexes=(PopupReflex("unit_detail", screens.UNIT_DETAIL, UNIT_DETAIL_FIX),),
    )

    outcomes = [loop.tick().outcome for _ in range(3)]

    assert outcomes == [TickOutcome.ACTED, TickOutcome.REFLEX, TickOutcome.ACTED]
    assert performed == ["survey", "survey"]


def test_the_journal_records_the_board_symbols_every_tick(tmp_path):
    unsynced = battle(allies=["a1"], enemies=["e1"], grid_on=False, board_synced=False)
    order = StageOrder(
        stage="S01",
        objectives=frozenset({Objective.CLEAR}),
        hidden_policy=HiddenPolicy.DECLINE,
        max_ticks=2,
    )
    journal = Journal(tmp_path / JOURNAL_NAME)
    loop = StageLoop(
        order,
        perceiver=ScriptedPerceiver([frame(unsynced)]),
        executor=LiveExecutor(device=FakeActuator(), sleep=lambda _: None),
        advisor=MockAdvisor(lambda current, action: None),
        victory=Annihilation(),
        journal=journal,
    )

    loop.tick()

    seen = journal.entries()[0]["seen"]
    assert seen["grid_on"] is False
    assert seen["board_synced"] is False
    assert seen["swept"] == []


@pytest.mark.parametrize("step", [ZOOM_STEP, MERGE_STEP])
def test_the_micro_step_names_are_stable_for_the_journal(step):
    assert isinstance(step, str) and step
