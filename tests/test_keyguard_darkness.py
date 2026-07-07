"""is_game_locked darkness gate: the lock-icon template TM_CCOEFF false-matches
a dark uniform patch of a stalled-but-live battle map, which used to trigger a
bogus unlock drag onto the map. Require whole-frame darkness (the real
battery-saver lock dims the entire screen) before trusting the icon."""

from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from ggge_ai.actuation.keyguard import GAME_LOCK_MAX_MEAN, GAME_LOCK_REGION, Keyguard

ROOT = Path(__file__).resolve().parents[1]
LOCK_TMPL = ROOT / "assets" / "templates" / "elements" / "game_lock_icon.png"


class _Device:
    def shell(self, *args, **kwargs):
        return SimpleNamespace(output="")


def _frame_with_icon(bg_value: int) -> np.ndarray:
    frame = np.full((1080, 2340, 3), bg_value, np.uint8)
    tmpl = cv2.imread(str(LOCK_TMPL))
    x, y, _, _ = GAME_LOCK_REGION
    frame[y : y + tmpl.shape[0], x : x + tmpl.shape[1]] = tmpl
    return frame


def _keyguard(frame: np.ndarray) -> Keyguard:
    return Keyguard(_Device(), capture=lambda: frame)


def test_dark_frame_with_icon_is_locked():
    frame = _frame_with_icon(bg_value=0)
    assert float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean()) < GAME_LOCK_MAX_MEAN
    assert _keyguard(frame).is_game_locked() is True


def test_bright_frame_with_icon_not_locked():
    # same icon present, but a bright frame -> the darkness gate rejects it
    # (this was the false positive on a stalled-but-live map)
    frame = _frame_with_icon(bg_value=200)
    assert _keyguard(frame).is_game_locked() is False


def test_gate_boundary_just_above_is_rejected():
    frame = _frame_with_icon(bg_value=int(GAME_LOCK_MAX_MEAN) + 20)
    assert _keyguard(frame).is_game_locked() is False
