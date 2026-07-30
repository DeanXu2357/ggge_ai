"""反射組：彈窗收乾、子模式退回、前景卡死看門狗，以及接進迴圈後的優先序。"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from ggge_ai.contracts import Ending, HiddenPolicy, Objective, StageOrder
from ggge_ai.runtime import reflexes, screens
from ggge_ai.runtime.device import Key, LiveExecutor, Tap
from ggge_ai.runtime.journal import Journal
from ggge_ai.runtime.perceive import Observation
from ggge_ai.stage.goals import Annihilation
from ggge_ai.stage.loop import StageLoop, TickOutcome
from ggge_ai.stage.run import JOURNAL_NAME
from tests.fixtures.frames import load
from tests.fixtures.stage_offline import MockAdvisor, ScriptedPerceiver, battle, kills_everything


def seen(screen: str, **evidence) -> Observation:
    return Observation(screen=screen, evidence=evidence)


@dataclass
class FakeActuator:
    taps: list[tuple[int, int, str]] = field(default_factory=list)
    keys: list[str] = field(default_factory=list)

    def tap(self, x: int, y: int, intent: str = "") -> None:
        self.taps.append((x, y, intent))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_s: float) -> None:
        raise AssertionError("反射組不該用 swipe")

    def key(self, keycode: str) -> None:
        self.keys.append(keycode)


def test_each_popup_reflex_only_fires_on_its_own_screen():
    for reflex in reflexes.default_reflexes():
        if not isinstance(reflex, reflexes.PopupReflex):
            continue
        assert reflex.match(seen(reflex.screen)) is reflex.fix
        assert reflex.match(seen(screens.BATTLE_MAP)) is None


def test_the_end_turn_dialog_always_takes_the_left_option_then_confirms():
    """紅線：左邊「待機並結束」，右邊自動戰鬥永遠不點。"""
    fix = reflexes.END_TURN_FIX

    assert [(g.x, g.y) for g in fix.gestures] == [
        reflexes.END_TURN_WAIT_TAP,
        reflexes.END_TURN_CONFIRM_TAP,
    ]
    assert all(g.x < 1400 or g.y > 700 for g in fix.gestures)


def test_the_login_and_notice_popups_are_dismissed_by_their_calibrated_taps():
    assert reflexes.LOGIN_BONUS_FIX.gestures[0].x == reflexes.LOGIN_BONUS_TAP[0]
    assert reflexes.NOTICE_FIX.gestures[0].y == reflexes.NOTICE_CLOSE_TAP[1]
    assert reflexes.DATE_CHANGED_FIX.gestures[0].x == reflexes.DATE_CHANGED_TAP[0]


@pytest.mark.parametrize(
    ("case", "reflex_name", "point"),
    [
        ("popups/login_bonus_dim_20260729", "login_bonus", reflexes.LOGIN_BONUS_TAP),
        ("popups/notice_loading_20260729", "notice", reflexes.NOTICE_CLOSE_TAP),
        ("popups/date_changed_hub_20260730", "date_changed", reflexes.DATE_CHANGED_TAP),
    ],
)
def test_a_real_popup_frame_reaches_its_reflex_and_gets_the_right_tap(case, reflex_name, point):
    """簽名補齊前這三個反射永遠等不到自己的畫面名（分類器只回 unknown）。
    實幀 → classify → 反射 → 收乾點，整條線一起釘住。"""
    observation = Observation(screen=screens.classify(load(case)))

    fired = [
        (reflex.name, reflex.match(observation))
        for reflex in reflexes.default_reflexes()
        if reflex.match(observation) is not None
    ]

    assert [name for name, _ in fired] == [reflex_name]
    fix = fired[0][1]
    assert [(g.x, g.y) for g in fix.gestures] == [point]


def test_the_notice_close_tap_lands_on_the_close_button_in_the_real_frame():
    """關閉鈕帶是實測位置：反射點的那一下必須落在按鈕框內（0723 標定）。"""
    frame = load("popups/notice_loading_20260729")
    x, y = reflexes.NOTICE_CLOSE_TAP

    assert screens.classify(frame) == screens.NOTICE
    # 按鈕框的內側亮底（藍灰），不是彈窗留白也不是黑幀。
    b, g, r = (int(v) for v in frame[y, x])
    assert 60 < b < 255 and 60 < g < 255 and 60 < r < 255


def test_a_stray_unit_move_mode_is_backed_out_of():
    """拖曳平移抓到單位會誤入移動模式（實測兩次）——返回鈕退出，不落子。"""
    reflex = next(r for r in reflexes.default_reflexes() if getattr(r, "name", "") == "unit_move")

    fix = reflex.match(seen(screens.BATTLE_UNIT_MOVE))

    assert fix is not None
    assert (fix.gestures[0].x, fix.gestures[0].y) == reflexes.BATTLE_RETURN_TAP


def test_the_watchdog_needs_a_streak_of_identical_frames():
    watchdog = reflexes.StallWatchdog(limit=3)

    assert watchdog.match(seen(screens.BATTLE_MAP, frame_sig="a")) is None
    assert watchdog.match(seen(screens.BATTLE_MAP, frame_sig="a")) is None
    fix = watchdog.match(seen(screens.BATTLE_MAP, frame_sig="a"))

    assert fix is not None
    assert fix.label == "recover:foreground"


def test_a_changing_frame_resets_the_watchdog():
    watchdog = reflexes.StallWatchdog(limit=3)

    for signature in ("a", "a", "b", "a", "a"):
        assert watchdog.match(seen(screens.BATTLE_MAP, frame_sig=signature)) is None


def test_the_watchdog_recovery_is_home_then_the_game_icon():
    watchdog = reflexes.StallWatchdog(limit=1)

    fix = watchdog.match(seen(screens.BATTLE_MAP, frame_sig="frozen"))

    assert isinstance(fix.gestures[0], Key)
    assert fix.gestures[0].keycode == "KEYCODE_HOME"
    assert (fix.gestures[1].x, fix.gestures[1].y) == reflexes.GAME_ICON_TAP


def test_the_watchdog_rearms_after_recovering():
    watchdog = reflexes.StallWatchdog(limit=2)
    watchdog.match(seen(screens.BATTLE_MAP, frame_sig="x"))

    assert watchdog.match(seen(screens.BATTLE_MAP, frame_sig="x")) is not None
    assert watchdog.match(seen(screens.BATTLE_MAP, frame_sig="x")) is None


def test_a_frame_with_no_signature_never_trips_the_watchdog():
    watchdog = reflexes.StallWatchdog(limit=2)

    for _ in range(5):
        assert watchdog.match(seen(screens.BATTLE_MAP)) is None


def test_a_popup_is_answered_before_any_planning_and_before_the_watchdog(tmp_path):
    order = StageOrder(
        stage="S01",
        objectives=frozenset({Objective.CLEAR}),
        hidden_policy=HiddenPolicy.DECLINE,
        max_ticks=4,
    )
    frames = [
        seen(screens.END_TURN_DIALOG, frame_sig="same"),
        Observation(
            screen=screens.BATTLE_MAP,
            state=battle(allies=["a1"], enemies=[], actionable=[]),
            terminal=Ending.VICTORY,
        ),
    ]
    actuator = FakeActuator()
    advisor = MockAdvisor(kills_everything())
    loop = StageLoop(
        order,
        perceiver=ScriptedPerceiver(frames),
        executor=LiveExecutor(device=actuator, sleep=lambda _: None),
        advisor=advisor,
        victory=Annihilation(),
        journal=Journal(tmp_path / JOURNAL_NAME),
        reflexes=reflexes.default_reflexes(),
    )

    first = loop.tick()

    assert first.outcome is TickOutcome.REFLEX
    assert first.reflex == "end_turn"
    assert first.did == "end_turn:wait"
    assert advisor.appraisals == 0
    assert [(x, y) for x, y, _ in actuator.taps] == [
        reflexes.END_TURN_WAIT_TAP,
        reflexes.END_TURN_CONFIRM_TAP,
    ]


def test_the_fixes_only_use_taps_keys_and_waits():
    for reflex in reflexes.default_reflexes():
        fix = reflex.match(seen(getattr(reflex, "screen", screens.BATTLE_MAP), frame_sig="s"))
        if fix is None:
            continue
        for gesture in fix.gestures:
            assert not isinstance(gesture, tuple), gesture
            assert isinstance(gesture, Tap | Key | reflexes.Settle)
