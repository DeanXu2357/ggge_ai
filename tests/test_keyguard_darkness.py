"""is_game_locked gates: the darkness gate (a dark uniform patch of a live
map must not read as the lock), and the faded-overlay poke (a dim iconless
frame is either the faded touch lock or a transition black frame -- a
neutral poke wakes the lock's icon back up, a transition stays iconless)."""

from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from ggge_ai.actuation import keyguard as keyguard_mod
from ggge_ai.actuation.keyguard import GAME_LOCK_MAX_MEAN, GAME_LOCK_REGION, Keyguard

ROOT = Path(__file__).resolve().parents[1]
LOCK_TMPL = ROOT / "assets" / "templates" / "elements" / "game_lock_icon.png"


class _Device:
    def __init__(self):
        self.shells = []

    def shell(self, cmd, *args, **kwargs):
        self.shells.append(cmd)
        return SimpleNamespace(output="")


def _frame_with_icon(bg_value: int) -> np.ndarray:
    frame = np.full((1080, 2340, 3), bg_value, np.uint8)
    tmpl = cv2.imread(str(LOCK_TMPL))
    x, y, _, _ = GAME_LOCK_REGION
    frame[y : y + tmpl.shape[0], x : x + tmpl.shape[1]] = tmpl
    return frame


def _dark_frame() -> np.ndarray:
    return np.full((1080, 2340, 3), 10, np.uint8)


def _keyguard(*frames: np.ndarray) -> Keyguard:
    feed = list(frames)
    return Keyguard(_Device(), capture=lambda: feed.pop(0) if len(feed) > 1 else feed[0])


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(keyguard_mod.time, "sleep", lambda *a: None)


def test_dark_frame_with_icon_is_locked():
    frame = _frame_with_icon(bg_value=0)
    assert float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean()) < GAME_LOCK_MAX_MEAN
    kg = _keyguard(frame)
    assert kg.is_game_locked() is True
    assert kg.device.shells == []  # icon visible outright, no poke needed


def test_bright_frame_with_icon_not_locked():
    # same icon present, but a bright frame -> the darkness gate rejects it
    # (this was the false positive on a stalled-but-live map)
    frame = _frame_with_icon(bg_value=200)
    assert _keyguard(frame).is_game_locked() is False


def test_gate_boundary_just_above_is_rejected():
    frame = _frame_with_icon(bg_value=int(GAME_LOCK_MAX_MEAN) + 20)
    assert _keyguard(frame).is_game_locked() is False


def test_faded_overlay_poke_wakes_icon_and_locks():
    # 2026-07-19 live: the overlay hides its icon after a few idle seconds
    # while still eating taps -- the poke wakes the icon, second look locks
    kg = _keyguard(_dark_frame(), _frame_with_icon(bg_value=0))
    assert kg.is_game_locked() is True
    assert kg.device.shells == [keyguard_mod.LOCK_POKE]


def test_transition_black_frame_stays_unlocked_after_poke():
    kg = _keyguard(_dark_frame(), _dark_frame())
    assert kg.is_game_locked() is False
    assert kg.device.shells == [keyguard_mod.LOCK_POKE]
