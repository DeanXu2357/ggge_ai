from __future__ import annotations

import copy
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from random import Random

from ggge_ai_2.agent.belief import Belief, UiSource
from ggge_ai_2.agent.contract import Evidence, Plan, Step
from ggge_ai_2.agent.generic_plans import (
    AutoOffPlan,
    PassingWaitPlan,
    PowerSaveLockPlan,
    TapToContinuePlan,
)
from ggge_ai_2.agent.stage_survey import differences, stage_data
from ggge_ai_2.agent.ui_steps import first_move, operation_step
from ggge_ai_2.mapgeom.contract import MapGeometry
from ggge_ai_2.planner.map_sync import MapSyncPlanner
from ggge_ai_2.stagedata.contract import StageData, StageStore
from ggge_ai_2.uisim.contract import Operation, UiAutoMode, UiScreen, UiSim

log = logging.getLogger(__name__)

GREEDY_BUTTONS: Mapping[UiScreen, str] = {
    UiScreen.BATTLE_INFO_PREVIEW: "battle_info_preview__tap_next",
    UiScreen.PLAYER_PHASE_OVERVIEW: "player_phase_overview__unit_card",
    UiScreen.SELECT_ACTION_IN_BATTLE: "select_action_in_battle__select_weapon",
    UiScreen.SELECT_WEAPON_IN_BATTLE: "select_weapon_in_battle__attack",
    UiScreen.BATTLE_PREP_ATTACK: "battle_prep_attack__start_battle",
    UiScreen.BATTLE_PREP_RESPONSE_ATTACK: "battle_prep_response_attack__start_battle",
    UiScreen.NON_PLAYER_PHASE_BATTLE_VIEW: "non_player_phase_battle_view__wait",
    UiScreen.CHALLENGE_BATTLE_CHECK: "challenge_battle_check__challenge",
    UiScreen.BATTLE_MAIN_SETTING: "battle_main_setting__close",
}
FALLBACK_WEAPON_BUTTON = "select_weapon_in_battle__wait"


class StageEntry(StrEnum):
    AUTO_CHECK = "auto_check"
    SURVEY_CHECK = "survey_check"
    PASSED = "passed"


ENTRY_HOLDS: Mapping[StageEntry, frozenset[UiScreen]] = {
    StageEntry.AUTO_CHECK: frozenset(
        {UiScreen.BATTLE_INFO_PREVIEW, UiScreen.PLAYER_PHASE_OVERVIEW}
    ),
    StageEntry.SURVEY_CHECK: frozenset({UiScreen.PLAYER_PHASE_OVERVIEW}),
    StageEntry.PASSED: frozenset(),
}


@dataclass(frozen=True)
class StageSurvey:
    store: StageStore
    stage: str
    app_version: str
    code_version: str
    resurvey: bool
    geometry: MapGeometry
    rng: Random


@dataclass(frozen=True)
class StagePlan:
    goal: UiScreen
    uisim: UiSim
    screen: tuple[int, int]
    auto_off: AutoOffPlan
    tap_to_continue: TapToContinuePlan
    fallback: bool = False
    power_save: PowerSaveLockPlan = PowerSaveLockPlan()
    passing_wait: PassingWaitPlan = PassingWaitPlan()
    entry: StageEntry = StageEntry.PASSED
    survey: MapSyncPlanner | None = None

    def still_valid(self, belief: Belief, evidence: Evidence) -> bool:
        if self.auto_off.awaiting_confirmation(belief):
            return False
        if self.survey is not None:
            return self.survey.still_valid(belief, evidence)
        if self._generic(belief, evidence) is not None:
            return True
        if belief.ui.screen in ENTRY_HOLDS[self.entry]:
            return False
        return self._operation(belief) is not None

    def next(self, belief: Belief, evidence: Evidence) -> Step:
        generic = self._generic(belief, evidence)
        if generic is not None:
            return generic.next(belief, evidence)
        if self.survey is not None:
            return self.survey.next(belief, evidence)
        operation = self._operation(belief)
        assert operation is not None, "the main loop takes a step only from a valid plan"
        return operation_step(operation, belief, self.uisim, self.screen)

    def _generic(self, belief: Belief, evidence: Evidence) -> Plan | None:
        order: tuple[Plan, ...] = (
            self.power_save,
            self.passing_wait,
            self.tap_to_continue,
            self.auto_off,
        )
        return next((plan for plan in order if plan.still_valid(belief, evidence)), None)

    def _operation(self, belief: Belief) -> Operation | None:
        screen = belief.ui.screen
        if self.fallback and screen is not UiScreen.SELECT_WEAPON_IN_BATTLE:
            return None
        if screen in GREEDY_BUTTONS:
            operations = {
                operation.name: operation for operation in self.uisim.successors(belief.ui)
            }
            if self.fallback:
                return operations.get(FALLBACK_WEAPON_BUTTON)
            return operations.get(GREEDY_BUTTONS[screen])
        if screen is self.goal:
            return None
        move = first_move(self.uisim, belief.ui, self.goal)
        return None if move is None else move[0]


@dataclass(frozen=True)
class StagePlanController:
    goal: UiScreen
    uisim: UiSim
    screen: tuple[int, int]
    stage_survey: StageSurvey | None = None

    def goal_reached(self, belief: Belief) -> bool:
        return (
            belief.ui_basis.source is UiSource.SEEN
            and belief.ui.screen is self.goal
            and belief.passing is None
        )

    def think(
        self, belief: Belief, evidence: Evidence, history: Sequence[object]
    ) -> StagePlan | None:
        previous = history[-1] if history and isinstance(history[-1], StagePlan) else None
        if previous is None:
            auto_off = AutoOffPlan(self.uisim, self.screen)
        else:
            auto_off = previous.auto_off.confirmed(belief)
        # The loop thinks again on a valid plan only after MISMATCH_LIMIT mismatches.
        # So a valid greedy plan on this screen means that '攻擊' did not change the
        # screen: no target is in range.
        fallback = (
            belief.ui.screen is UiScreen.SELECT_WEAPON_IN_BATTLE
            and previous is not None
            and not previous.fallback
            and previous.still_valid(belief, evidence)
        )
        entry, survey = self._entry(previous, belief, evidence)
        # TODO: after CONFIRMED, think keeps the greedy plan. The strategy after AUTO is
        #     not decided.
        plan = StagePlan(
            self.goal,
            self.uisim,
            self.screen,
            auto_off,
            TapToContinuePlan(self.screen),
            fallback,
            entry=entry,
            survey=survey,
        )
        return plan if plan.still_valid(belief, evidence) else None

    def review(self, plan: StagePlan, belief: Belief) -> object:
        return replace(plan, auto_off=copy.copy(plan.auto_off))

    def _entry(
        self, previous: StagePlan | None, belief: Belief, evidence: Evidence
    ) -> tuple[StageEntry, MapSyncPlanner | None]:
        setup = self.stage_survey
        if setup is None:
            return StageEntry.PASSED, None
        if previous is None:
            entry, survey = StageEntry.AUTO_CHECK, None
        else:
            entry, survey = previous.entry, previous.survey
        screen = belief.ui.screen
        if survey is not None:
            if not survey.finished(evidence):
                return entry, survey
            judgment = survey.judgment(evidence)
            assert judgment is not None, "a finished survey has a judgment"
            self._settle(
                setup, stage_data(judgment, setup.stage, setup.app_version, setup.code_version)
            )
            return entry, None
        # A unit does not move while AUTO is off on the battle info preview. On the map
        # AUTO can move a unit before the plan turns AUTO off.
        if entry is StageEntry.AUTO_CHECK and screen is UiScreen.BATTLE_INFO_PREVIEW:
            if belief.ui.auto is UiAutoMode.MANUAL:
                return StageEntry.SURVEY_CHECK, None
            return entry, None
        if entry is StageEntry.SURVEY_CHECK and screen is UiScreen.PLAYER_PHASE_OVERVIEW:
            stored = setup.store.load(setup.stage, setup.app_version)
            if stored is not None and not setup.resurvey:
                return StageEntry.PASSED, None
            start = len(evidence.map_readings)
            sync = MapSyncPlanner(
                setup.stage, start, setup.geometry, self.uisim, self.screen, setup.rng
            )
            return StageEntry.PASSED, sync
        return entry, None

    def _settle(self, setup: StageSurvey, surveyed: StageData) -> None:
        stored = setup.store.load(setup.stage, setup.app_version)
        if stored is None:
            setup.store.save(surveyed)
            log.info("stage data saved", extra={"stage": setup.stage})
            return
        found = differences(stored, surveyed)
        if found:
            log.error(
                "stage data differs", extra={"stage": setup.stage, "differences": list(found)}
            )
        else:
            log.info("stage data matches", extra={"stage": setup.stage})
