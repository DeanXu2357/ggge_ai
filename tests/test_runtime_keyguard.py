"""兩種鎖：系統鎖的 dumpsys 判定、省電鎖的暗幀＋圖示＋戳一下複驗。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from ggge_ai.runtime import keyguard as kg


@dataclass
class FakeShell:
    locked: bool = False
    commands: list[str] = field(default_factory=list)

    def __call__(self, command: str) -> str:
        self.commands.append(command)
        if "dumpsys" in command:
            return "mIsShowing=true" if self.locked else "mIsShowing=false"
        if "dismiss-keyguard" in command or "KEYCODE_WAKEUP" in command:
            self.locked = False
        return ""


def lock_icon() -> np.ndarray:
    icon = cv2.imread(str(kg.TEMPLATE))
    assert icon is not None, "省電鎖圖示模板不見了"
    return icon


def dim_frame_with_icon() -> np.ndarray:
    frame = np.full((1080, 2340, 3), 14, np.uint8)
    icon = lock_icon()
    x, y, _, _ = kg.REGION
    frame[y : y + icon.shape[0], x : x + icon.shape[1]] = icon
    return frame


def dim_frame() -> np.ndarray:
    return np.full((1080, 2340, 3), 14, np.uint8)


def bright_frame_with_icon() -> np.ndarray:
    frame = np.full((1080, 2340, 3), 90, np.uint8)
    icon = lock_icon()
    x, y, _, _ = kg.REGION
    frame[y : y + icon.shape[0], x : x + icon.shape[1]] = icon
    return frame


def guard(frames, shell=None):
    seen = iter(frames)
    shell = shell or FakeShell()
    return (
        kg.Keyguard(shell=shell, capture=lambda: next(seen, frames[-1]), sleep=lambda _: None),
        shell,
    )


def test_the_template_ships_with_the_repo():
    assert Path(kg.TEMPLATE).exists()


def test_the_system_keyguard_is_read_off_dumpsys():
    locked, _ = guard([dim_frame()], shell=FakeShell(locked=True))
    unlocked, _ = guard([dim_frame()], shell=FakeShell(locked=False))

    assert locked.is_locked() is True
    assert unlocked.is_locked() is False


def test_a_dim_frame_showing_the_lock_icon_is_the_battery_saver_lock():
    lock, _ = guard([dim_frame_with_icon()])

    assert lock.is_game_locked() is True


def test_a_bright_map_is_never_the_lock_even_when_the_icon_seems_to_match():
    """TM_CCOEFF_NORMED 會在還活著的暗地圖均勻塊上假命中（0706 事故：假鎖的
    拖曳在地圖單位上開了面板）。整幀亮度是第二道閘。"""
    lock, shell = guard([bright_frame_with_icon()])

    assert lock.is_game_locked() is False
    assert shell.commands == []


def test_a_dim_iconless_frame_is_poked_before_it_is_believed():
    """覆蓋層淡出後只剩變暗、tap 照樣被吞（0719 兩輪偵察死在這裡）：戳一下把
    圖示叫回來才算數，真的過場黑幀不理這一戳。"""
    lock, shell = guard([dim_frame(), dim_frame_with_icon()])

    assert lock.is_game_locked() is True
    assert kg.LOCK_POKE in shell.commands


def test_a_transition_black_frame_ignores_the_poke_and_is_not_a_lock():
    lock, shell = guard([dim_frame(), dim_frame()])

    assert lock.is_game_locked() is False
    assert kg.LOCK_POKE in shell.commands


def test_ensure_unlocked_does_nothing_when_nothing_is_locked():
    lock, shell = guard([bright_frame_with_icon()], shell=FakeShell(locked=False))

    assert lock.ensure_unlocked() is True
    assert [c for c in shell.commands if "swipe" in c] == []


def test_ensure_unlocked_drags_the_lock_icon_for_both_locks():
    frames = [dim_frame_with_icon(), dim_frame_with_icon(), bright_frame_with_icon()]
    lock, shell = guard(frames, shell=FakeShell(locked=True))

    lock.ensure_unlocked()

    assert kg.LOCK_DRAG in shell.commands


def test_a_lock_that_will_not_go_away_is_reported_as_failure():
    lock, _ = guard([dim_frame_with_icon()], shell=FakeShell(locked=False))

    assert lock.dismiss_game_lock(attempts=2) is False


def test_no_frame_at_all_is_not_a_lock():
    lock = kg.Keyguard(shell=FakeShell(), capture=lambda: None, sleep=lambda _: None)

    assert lock.is_game_locked() is False
