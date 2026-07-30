"""行動 → 手勢：已標定的流程接得動，沒標定的大聲拒絕。"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from ggge_ai.runtime.device import LiveExecutor, TapRefused, UnsupportedAction, check_tap
from ggge_ai.runtime.entry import ABANDON_CONFIRM_TAP, BATTLE_MENU_ABANDON_TAP, BATTLE_MENU_TAP
from ggge_ai.runtime.perceive import Observation
from ggge_ai.stage import gestures
from ggge_ai.stage.actions import Attack, Brace, Move, Withdraw


@dataclass
class FakeActuator:
    taps: list[tuple[int, int, str]] = field(default_factory=list)

    def tap(self, x: int, y: int, intent: str = "") -> None:
        check_tap(x, y, intent)
        self.taps.append((x, y, intent))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_s: float) -> None:
        raise AssertionError("本批的行動都不用 swipe")

    def key(self, keycode: str) -> None:
        raise AssertionError("本批的行動都不用按鍵")


def executor(actuator=None) -> LiveExecutor:
    return LiveExecutor(
        device=actuator or FakeActuator(), plans=gestures.battle_plans(), sleep=lambda _: None
    )


def frame() -> Observation:
    return Observation(screen="battle_map")


def test_withdraw_walks_the_calibrated_surrender_flow():
    actuator = FakeActuator()

    executor(actuator).perform(Withdraw(), frame())

    assert [(x, y) for x, y, _ in actuator.taps] == [
        BATTLE_MENU_TAP,
        BATTLE_MENU_ABANDON_TAP,
        ABANDON_CONFIRM_TAP,
    ]


def test_withdraw_is_the_only_thing_carrying_the_abandon_intent():
    actuator = FakeActuator()

    executor(actuator).perform(Withdraw(), frame())

    assert [intent for _, _, intent in actuator.taps] == ["", "abandon", ""]


def test_the_abandon_button_stays_refused_without_that_intent():
    """放棄鈕在危險帶內：只有棄戰流程進得去，其他步驟一律拒點。"""
    with pytest.raises(TapRefused):
        check_tap(*BATTLE_MENU_ABANDON_TAP)


@pytest.mark.parametrize(
    ("stance", "point"),
    [
        ("dodge", gestures.STANCE_DODGE_TAP),
        ("defend", gestures.STANCE_DEFEND_TAP),
        ("shield", gestures.STANCE_DEFEND_TAP),
    ],
)
def test_a_calibrated_stance_taps_its_fixed_slot_then_confirms(stance, point):
    """動作列是固定槽位格、右錨不動（0719 像素實證）：閃避最右、防禦左一格，
    有盾機體換圖示不換位置。"""
    actuator = FakeActuator()

    executor(actuator).perform(Brace("a1", "e1", stance), frame())

    assert [(x, y) for x, y, _ in actuator.taps] == [point, gestures.REACTION_CONFIRM_TAP]


def test_a_counter_stance_is_refused_because_its_slot_needs_a_menu_read():
    """counter 的槽位要讀選單（EN 黃字定佔用）才知道；沒接就拒絕，不亂點一格。"""
    with pytest.raises(UnsupportedAction):
        executor().perform(Brace("a1", "e1", "counter:光束軍刀"), frame())


@pytest.mark.parametrize("action", [Move("a1", (3, 4)), Attack("a1", "e1")])
def test_the_actions_that_still_need_board_alignment_are_loudly_unsupported(action):
    with pytest.raises(UnsupportedAction):
        executor().perform(action, frame())


def test_the_stance_slots_march_left_at_the_measured_pitch():
    """標定的兩錨點差 188px、文件記的 pitch 是 187——差一像素，兩者都在同一格內。"""
    gap = gestures.STANCE_DODGE_TAP[0] - gestures.STANCE_DEFEND_TAP[0]

    assert abs(gap - gestures.STANCE_PITCH) <= 1
    assert gestures.STANCE_DODGE_TAP[1] == gestures.STANCE_ROW_Y


def test_the_reaction_confirm_needs_a_deliberate_intent():
    """行動選擇 (2042,924) 與出擊準備的自動編制 (2001,924) 共用一塊區域。"""
    with pytest.raises(TapRefused):
        check_tap(*gestures.REACTION_CONFIRM_TAP)

    check_tap(*gestures.REACTION_CONFIRM_TAP, intent=gestures.CONFIRM_INTENT)

    with pytest.raises(TapRefused):
        check_tap(2001, 924, intent="")
