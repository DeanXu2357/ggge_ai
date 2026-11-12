from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from pathlib import Path
from random import Random

import numpy as np
import pytest

from ggge_ai_2.agent.belief import Belief, ScreenLock, UiBasis, UiSource
from ggge_ai_2.agent.contract import Evidence, MapReadingRecord
from ggge_ai_2.agent.generic_plans import AutoOffPlan, TapToContinuePlan
from ggge_ai_2.agent.stage_plan_controller import (
    StageEntry,
    StagePlan,
    StagePlanController,
    StageSurvey,
)
from ggge_ai_2.agent.stage_survey import stage_data
from ggge_ai_2.mapgeom import contract as geo
from ggge_ai_2.mapparser.contract import MapPhase, MapReading
from ggge_ai_2.planner.map_sync import MapSyncPlanner
from ggge_ai_2.stagedata.contract import StageData
from ggge_ai_2.stream.contract import StillWindow
from ggge_ai_2.uisim.contract import UiAutoMode, UiScreen, UiState
from ggge_ai_2.uisim.stage_sim import StageUiSim
from ggge_ai_2.uisim.stages import load_stages
from tests.ggge_ai_2.fakes.domain import FakeDomain

REAL_STAGES = Path(__file__).resolve().parents[4] / "assets" / "ui_stages" / "stages.json"
BATTLE_SIM = StageUiSim(load_stages(REAL_STAGES))
SCREEN = (2340, 1080)
GOAL = UiScreen.DROP_REWARD_RESULT
PREVIEW = UiScreen.BATTLE_INFO_PREVIEW
OVERVIEW = UiScreen.PLAYER_PHASE_OVERVIEW
STAGE = "story-1-1-hard"
APP_VERSION = "1.4.0"
NO_READINGS = Evidence(())
FULL, MANUAL = UiAutoMode.FULL, UiAutoMode.MANUAL


@dataclass
class MockStageStore:
    stored: dict[tuple[str, str], StageData] = field(default_factory=dict)

    def load(self, stage: str, app_version: str) -> StageData | None:
        return self.stored.get((stage, app_version))

    def save(self, data: StageData) -> None:
        self.stored[(data.stage, data.app_version)] = data


@dataclass(frozen=True)
class MockMapGeometry:
    judgment: geo.MapJudgment | None

    def judge(self, views: object) -> geo.MapJudgment | None:
        return self.judgment


def on(screen: UiScreen, auto: UiAutoMode | None = MANUAL, at: float = 10.0) -> Belief:
    return Belief(
        UiState(screen, auto=auto), UiBasis(UiSource.SEEN, int(at)), FakeDomain(), still(at)
    )


def still(at: float) -> StillWindow:
    return StillWindow(at - 0.5, at, int(at))


def readings(*times: float) -> Evidence:
    empty = MapReading(None, 1, MapPhase.PLAYER, {}, frozenset(), (), {}, None, None)
    return Evidence(tuple(MapReadingRecord(still(at), empty) for at in times))


def brief(seed: int, hp: int = 5000) -> geo.UnitBrief:
    def name(offset: int) -> geo.NameMask:
        rng = np.random.default_rng(seed + offset)
        return geo.NameMask(rng.integers(0, 2, (14, 60), np.uint8) * 255)

    return geo.UnitBrief(
        geo.UnitRole.ATTACK,
        name(0),
        hp,
        120,
        geo.UnitRole.NO_ROLE,
        name(1000),
        30,
        40,
        geo.PilotState.STRONG,
    )


def board(hp: int = 5000, uncertain: frozenset[geo.MapCell] = frozenset()) -> geo.MapJudgment:
    enemy = geo.MapUnit(False, geo.Faction.ENEMY, brief(1, hp))
    sortie = geo.MapUnit(True, None, None)
    return geo.MapJudgment(
        stage=None,
        turn=1,
        phase=geo.ViewPhase.PLAYER,
        columns=geo.Axis(4, True, True),
        rows=geo.Axis(3, True, True),
        cells={},
        uncertain=uncertain,
        unit_cells={(1, 1): 0, (2, 0): 1},
        units={0: enemy, 1: sortie},
        current=frozenset({(0, 0)}),
    )


def survey(
    store: MockStageStore, judged: geo.MapJudgment | None = None, resurvey: bool = False
) -> StageSurvey:
    return StageSurvey(
        store, STAGE, APP_VERSION, "9416000a", resurvey, MockMapGeometry(judged), Random(0)
    )


def controller(setup: StageSurvey) -> StagePlanController:
    return StagePlanController(GOAL, BATTLE_SIM, SCREEN, setup)


def stage_plan(entry: StageEntry, setup: StageSurvey, surveying: bool = False) -> StagePlan:
    sync = MapSyncPlanner(STAGE, 0, setup.geometry, BATTLE_SIM, SCREEN, setup.rng)
    return StagePlan(
        GOAL,
        BATTLE_SIM,
        SCREEN,
        AutoOffPlan(BATTLE_SIM, SCREEN),
        TapToContinuePlan(SCREEN),
        entry=entry,
        survey=sync if surveying else None,
    )


def test_a_manual_battle_info_preview_passes_the_auto_check():
    plan = controller(survey(MockStageStore())).think(on(PREVIEW), NO_READINGS, [])

    assert plan is not None
    assert plan.entry is StageEntry.SURVEY_CHECK
    assert plan.next(on(PREVIEW), NO_READINGS).name == "battle_info_preview__tap_next"


def test_an_unread_auto_mode_on_the_battle_info_preview_halts():
    assert controller(survey(MockStageStore())).think(on(PREVIEW, None), NO_READINGS, []) is None


def test_auto_on_the_battle_info_preview_goes_off_before_the_tap_next():
    stage = controller(survey(MockStageStore()))
    live = stage.think(on(PREVIEW, FULL, 10.0), NO_READINGS, [])
    assert live is not None
    assert live.next(on(PREVIEW, FULL, 10.0), NO_READINGS).name == "battle_info_preview__auto"

    manual = on(PREVIEW, MANUAL, 11.0)
    assert not live.still_valid(manual, NO_READINGS)
    thought = stage.think(manual, NO_READINGS, [stage.review(live, manual)])

    assert thought is not None
    assert thought.next(manual, NO_READINGS).name == "battle_info_preview__tap_next"


def test_the_overview_without_the_auto_check_halts():
    assert controller(survey(MockStageStore())).think(on(OVERVIEW), NO_READINGS, []) is None


def test_a_run_that_checked_auto_by_hand_starts_the_survey_on_the_overview():
    setup = replace(survey(MockStageStore()), auto_checked=True)

    plan = controller(setup).think(on(OVERVIEW, at=3.0), readings(1.0, 2.0, 3.0), [])

    assert plan is not None and plan.survey is not None
    assert plan.survey.start == 3


def test_a_plan_before_the_survey_decision_is_invalid_on_the_overview():
    setup = survey(MockStageStore())

    assert not stage_plan(StageEntry.SURVEY_CHECK, setup).still_valid(on(OVERVIEW), NO_READINGS)


def test_a_stage_without_data_goes_to_the_survey():
    setup = survey(MockStageStore())
    previous = stage_plan(StageEntry.SURVEY_CHECK, setup)

    plan = controller(setup).think(on(OVERVIEW, at=3.0), readings(1.0, 2.0, 3.0), [previous])

    assert plan is not None and plan.survey is not None
    assert plan.survey.start == 3
    assert plan.next(on(OVERVIEW, at=3.0), readings(1.0, 2.0, 3.0)).name == "map_sync_wait"


def test_a_stage_with_data_skips_the_survey():
    store = MockStageStore()
    store.save(stage_data(board(), STAGE, APP_VERSION, "aaaaaaaa"))
    setup = survey(store)

    plan = controller(setup).think(
        on(OVERVIEW), NO_READINGS, [stage_plan(StageEntry.SURVEY_CHECK, setup)]
    )

    assert plan is not None and plan.survey is None
    assert plan.next(on(OVERVIEW), NO_READINGS).name == "player_phase_overview__unit_card"


def test_a_resurvey_surveys_a_stage_with_data():
    store = MockStageStore()
    store.save(stage_data(board(), STAGE, APP_VERSION, "aaaaaaaa"))
    setup = survey(store, resurvey=True)

    plan = controller(setup).think(
        on(OVERVIEW), NO_READINGS, [stage_plan(StageEntry.SURVEY_CHECK, setup)]
    )

    assert plan is not None and plan.survey is not None


def test_an_unfinished_survey_goes_on_after_a_rethink():
    setup = survey(MockStageStore(), board(uncertain=frozenset({(3, 2)})))
    previous = stage_plan(StageEntry.PASSED, setup, surveying=True)

    plan = controller(setup).think(on(OVERVIEW, at=1.0), readings(1.0), [previous])

    assert plan is not None
    assert plan.survey is previous.survey


def test_a_finished_survey_of_a_stage_without_data_saves_it():
    store = MockStageStore()
    setup = survey(store, board())

    plan = controller(setup).think(
        on(OVERVIEW, at=1.0), readings(1.0), [stage_plan(StageEntry.PASSED, setup, surveying=True)]
    )

    saved = store.load(STAGE, APP_VERSION)
    assert saved is not None
    assert (saved.code_version, [unit.pos for unit in saved.units]) == ("9416000a", [(1, 1)])
    assert plan is not None and plan.survey is None
    assert plan.next(on(OVERVIEW), NO_READINGS).name == "player_phase_overview__unit_card"


def test_a_finished_resurvey_that_differs_logs_an_error(caplog: pytest.LogCaptureFixture):
    store = MockStageStore()
    store.save(stage_data(board(5000), STAGE, APP_VERSION, "aaaaaaaa"))
    setup = survey(store, board(5100), resurvey=True)

    with caplog.at_level(logging.INFO):
        controller(setup).think(
            on(OVERVIEW, at=1.0),
            readings(1.0),
            [stage_plan(StageEntry.PASSED, setup, surveying=True)],
        )

    errors = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert [record.getMessage() for record in errors] == ["stage data differs"]
    assert errors[0].__dict__["differences"] == ["unit (1, 1): hp 5000 -> 5100"]
    stored = store.load(STAGE, APP_VERSION)
    assert stored is not None and stored.code_version == "aaaaaaaa"


def test_a_finished_resurvey_that_matches_logs_no_error(caplog: pytest.LogCaptureFixture):
    store = MockStageStore()
    store.save(stage_data(board(), STAGE, APP_VERSION, "aaaaaaaa"))
    setup = survey(store, board(), resurvey=True)

    with caplog.at_level(logging.INFO):
        controller(setup).think(
            on(OVERVIEW, at=1.0),
            readings(1.0),
            [stage_plan(StageEntry.PASSED, setup, surveying=True)],
        )

    assert not [record for record in caplog.records if record.levelno >= logging.WARNING]


def test_a_lock_frame_in_the_survey_gives_the_unlock_step():
    setup = survey(MockStageStore(), board(uncertain=frozenset({(3, 2)})))
    locked = replace(on(OVERVIEW, at=1.0), screen_lock=ScreenLock.ICON)

    step = stage_plan(StageEntry.PASSED, setup, surveying=True).next(locked, readings(1.0))

    assert step.name == "power_save_unlock"
