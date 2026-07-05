from __future__ import annotations

import logging
import time
from collections.abc import Callable

from ...core.action import Action, ExecutionContext
from ...perception.base import GameState
from .. import screens

logger = logging.getLogger(__name__)

# Reference coordinates (2340x1080) for taps without a dedicated template.
STORY_MENU = (2100, 49)
STORY_SKIP = (2103, 430)
AUTO_BUTTON = (1820, 54)
REWARD_CONTINUE = (2024, 1024)
POPUP_NEXT = (1170, 540)
HINT_ADVANCE = (1275, 590)

AUTO_STATE_IDS = ("btn_auto_full", "btn_auto_enemy", "btn_auto_manual")


def _poll(
    ctx: ExecutionContext,
    predicate: Callable[[GameState], bool],
    timeout: float,
    interval: float = 2.0,
) -> GameState | None:
    deadline = time.monotonic() + timeout
    last: GameState | None = None
    while time.monotonic() < deadline:
        last = ctx.perception.observe()
        if predicate(last):
            return last
        time.sleep(interval)
    return last


def _tap_element(ctx: ExecutionContext, element_id: str, fallback: tuple[int, int]) -> None:
    found = ctx.perception.probe([element_id]).get(element_id)
    if found is not None and found.confidence >= 0.85:
        ctx.actuator.tap(*found.bbox.center)
    else:
        ctx.actuator.tap(*fallback)


def _locate_story_menu(ctx: ExecutionContext) -> tuple[int, int] | None:
    from ...battle.vision import locate_story_menu

    return locate_story_menu(ctx.perception.capture())


def _skip_story_once(ctx: ExecutionContext) -> None:
    """Open the story MENU and hit SKIP. Safe to call repeatedly."""
    menu_x, menu_y = _locate_story_menu(ctx) or STORY_MENU
    ctx.actuator.tap(menu_x, menu_y)
    time.sleep(1.2)
    ctx.actuator.tap(menu_x, STORY_SKIP[1])
    time.sleep(2.0)


def try_skip_story(ctx: ExecutionContext) -> bool:
    """Skip a story only when the MENU button is really there; safe to
    fire on unclassified screens (used by the agent's unknown handler)."""
    located = _locate_story_menu(ctx)
    if located is None:
        return False
    logger.info("story menu found at %s during unknown screen, skipping", located)
    ctx.actuator.tap(*located)
    time.sleep(1.2)
    ctx.actuator.tap(located[0], STORY_SKIP[1])
    time.sleep(2.0)
    return True


def _dismiss_hint(ctx: ExecutionContext) -> None:
    """Close any coach-mark tutorial dialogue overlaying a menu. Only taps
    when the hint is actually detected, so it is a no-op on clean screens."""
    for _ in range(5):
        if ctx.perception.probe(["hint_dialog"]).get("hint_dialog") is None:
            return
        ctx.actuator.tap(*HINT_ADVANCE)
        time.sleep(1.2)


class EnterSortiePrep(Action):
    name = "enter_sortie_prep"
    preconditions = {"screen": screens.STAGE_LIST}
    effects = {"screen": screens.UNIT_SETUP}

    def execute(self, ctx: ExecutionContext) -> bool:
        _dismiss_hint(ctx)
        _tap_element(ctx, "btn_sortie_prep", (2035, 880))
        got = _poll(ctx, lambda g: g.screen == screens.UNIT_SETUP, timeout=15)
        return got is not None and got.screen == screens.UNIT_SETUP


class LaunchSortie(Action):
    """Tap 出擊, clear the first-time data-download popup if it appears, and
    wait until the pre-battle story (or the battle itself) is reached."""

    name = "launch_sortie"
    preconditions = {"screen": screens.UNIT_SETUP}
    effects = {"screen": screens.STORY}

    def execute(self, ctx: ExecutionContext) -> bool:
        _tap_element(ctx, "btn_launch", (2042, 1030))
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if ctx.perception.probe(["btn_download"]).get("btn_download", None) is not None:
                logger.info("download popup detected, confirming")
                _tap_element(ctx, "btn_download", (1369, 851))
                time.sleep(3)
                continue
            screen = ctx.perception.observe().screen
            if screen in (screens.STORY, screens.BATTLE_MAP):
                return True
            time.sleep(2)
        return True


class SkipStory(Action):
    """Drain one or more consecutive pre-battle story dialogues until the
    battle map (or an already-finished battle) is reached."""

    name = "skip_story"
    preconditions = {"screen": screens.STORY}
    effects = {"screen": screens.BATTLE_MAP}
    _targets = (screens.BATTLE_MAP, screens.BATTLE_RESULT)

    def execute(self, ctx: ExecutionContext) -> bool:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            screen = ctx.perception.observe().screen
            if screen in self._targets:
                return True
            if screen == screens.STORY:
                _skip_story_once(ctx)
            else:
                time.sleep(2)  # loading / transition
        return False


class ManualBattle(Action):
    """Fight the battle with our own controller instead of the built-in AI.

    Delegates to ManualBattleController: forces the AUTO toggle to
    colorless full manual on the first controllable frame, then drives
    every unit with the v1 heuristic (attack in range, otherwise advance
    toward the enemy force, otherwise stand by) and confirms enemy-turn
    engagements. stage_cleared is latched once the result screen appears."""

    name = "manual_battle"
    cost = 5.0
    preconditions = {"screen": screens.BATTLE_MAP}
    effects = {"screen": screens.BATTLE_RESULT, "stage_cleared": True}

    def execute(self, ctx: ExecutionContext) -> bool:
        from ...actuation.keyguard import Keyguard
        from ...battle.controller import ManualBattleController

        keyguard = (
            Keyguard(ctx.actuator.device, capture=ctx.perception.capture)
            if hasattr(ctx.actuator, "device")
            else None
        )
        blackboard = ctx.extras.get("blackboard")
        ledger = blackboard.new_ledger() if blackboard is not None else None
        controller = ManualBattleController(
            perception=ctx.perception, actuator=ctx.actuator, keyguard=keyguard, ledger=ledger
        )
        try:
            result = controller.run()
        finally:
            if blackboard is not None and ledger is not None:
                if ledger.outcome is None:
                    ledger.finish("interrupted")
                blackboard.archive(ledger)
        return result == screens.BATTLE_RESULT


class DismissResult(Action):
    name = "dismiss_result"
    preconditions = {"screen": screens.BATTLE_RESULT}
    effects = {"screen": screens.REWARD}

    def execute(self, ctx: ExecutionContext) -> bool:
        _tap_element(ctx, "btn_result_continue", REWARD_CONTINUE)
        got = _poll(ctx, lambda g: g.screen == screens.REWARD, timeout=15)
        return got is not None and got.screen == screens.REWARD


class ReturnToStageList(Action):
    """Drain the whole post-battle tail (reward lists, character-unlock
    popups, post-battle story, loading) until the stage list returns."""

    name = "return_to_stage_list"
    preconditions = {"screen": screens.REWARD}
    effects = {"screen": screens.STAGE_LIST}
    # the reward-continue corner coordinate doubles as the 選單 nav button
    # once a nav screen is back, so an overshoot tap can land us anywhere in
    # the main navigation - these recovery steps walk back to the stage list
    # nav_stage's template captures the lit state, so give every nav screen
    # the fixed bottom-bar coordinate as fallback for the unlit button
    _NAV_STAGE = ("nav_stage", (1230, 1050))
    _recovery = {
        screens.MENU: _NAV_STAGE,
        screens.MAIN_MENU: _NAV_STAGE,
        screens.ENHANCE: _NAV_STAGE,
        screens.DEVELOP: _NAV_STAGE,
        screens.BASE: _NAV_STAGE,
        screens.SUPPLY: _NAV_STAGE,
        screens.STAGE_TYPE_SELECT: ("btn_main_stage", None),
        screens.SERIES_SELECT: ("series_g_thumb", None),
        screens.SERIES_CONFIRM: ("btn_select", (1989, 889)),
    }

    def _tap_floating_series(self, ctx: ExecutionContext) -> None:
        """The series carousel floats and drifts, so the fixed probe
        threshold misses. Take the best template location wherever it is;
        with nothing plausible, tap the screen center (focused series)."""
        import cv2

        logger.info("overshot to series_select, locating series thumb")
        frame = ctx.perception.capture()
        template = cv2.imread("assets/templates/elements/series_g_thumb.png")
        result = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(result)
        if score >= 0.5:
            h, w = template.shape[:2]
            ctx.actuator.tap(loc[0] + w // 2, loc[1] + h // 2)
        else:
            ctx.actuator.tap(1170, 540)

    def execute(self, ctx: ExecutionContext) -> bool:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            state = ctx.perception.observe()
            screen = state.screen
            if screen == screens.STAGE_LIST:
                return True
            if screen == screens.STORY:
                ctx.actuator.tap(*STORY_MENU)
                time.sleep(1.2)
                ctx.actuator.tap(*STORY_SKIP)
            elif screen == screens.SERIES_SELECT and state.screen_confidence >= 0.9:
                self._tap_floating_series(ctx)
            elif screen in self._recovery and state.screen_confidence >= 0.9:
                element_id, fallback = self._recovery[screen]
                logger.info("overshot to %s, recovering via %s", screen, element_id)
                found = ctx.perception.probe([element_id])
                if element_id in found and found[element_id].confidence >= 0.85:
                    ctx.actuator.tap(*found[element_id].bbox.center)
                elif fallback:
                    ctx.actuator.tap(*fallback)
            elif screen in (screens.REWARD, screens.BATTLE_RESULT):
                # probe right before tapping to shrink the race window in
                # which the screen changes under a blind corner tap
                found = ctx.perception.probe(["btn_result_continue"])
                if "btn_result_continue" in found:
                    ctx.actuator.tap(*found["btn_result_continue"].bbox.center)
                else:
                    ctx.actuator.tap(*REWARD_CONTINUE)
            else:
                ctx.actuator.tap(*POPUP_NEXT)
            time.sleep(2.5)
        return False


CLEAR_STAGE_ACTIONS: list[Action] = [
    EnterSortiePrep(),
    LaunchSortie(),
    SkipStory(),
    ManualBattle(),
    DismissResult(),
    ReturnToStageList(),
]
