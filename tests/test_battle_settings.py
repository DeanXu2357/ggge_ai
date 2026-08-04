"""顯示方格 settings driver (#25): probe-verified toggling with the
AUTO戰鬥 red-line guard, fail-soft escapes, and lattice snapping."""

from __future__ import annotations

import numpy as np

from ggge_ai.battle import settings, vision


def _settings_frame(*, grid_on: bool, auto_off: bool = True, tab: bool = True) -> np.ndarray:
    frame = np.zeros((1080, 2340, 3), np.uint8)
    gx, gy = settings.GRID_PROBE
    frame[gy, gx] = (200, 190, 100) if grid_on else (90, 90, 90)
    ax, ay = settings.AUTO_BATTLE_OFF_PROBE
    if auto_off:
        frame[ay, ax] = (250, 240, 120)
    if tab:
        # 底線畫成「有邊界的色塊」：偵測器要的是端點落在籤寬上的鮭色連續段，
        # 不是單一鮭色像素，也不是無限延伸的一列
        x0, x1 = settings.BATTLE_TAB_UNDERLINE_EDGES
        frame[settings.BATTLE_TAB_UNDERLINE[1], x0 : x1 + 1] = (160, 180, 240)
    return frame


class _Driver:
    def __init__(self, frames):
        self.frames = list(frames)
        self.taps = []

    def capture(self):
        return self.frames.pop(0) if len(self.frames) > 1 else self.frames[0]

    def tap(self, x, y):
        self.taps.append((x, y))


def test_toggle_off_to_on_taps_and_verifies():
    d = _Driver([_settings_frame(grid_on=False), _settings_frame(grid_on=True)])
    ok = settings.set_battle_grid(d.capture, d.tap, True, sleep=lambda s: None)
    assert ok is True
    assert settings.GRID_TOGGLE in d.taps
    # menus are always closed on the way out
    assert d.taps[-2:] == [settings.SETTINGS_CLOSE, settings.BATTLE_MENU_CLOSE]


def test_already_desired_state_skips_the_toggle():
    d = _Driver([_settings_frame(grid_on=True)])
    ok = settings.set_battle_grid(d.capture, d.tap, True, sleep=lambda s: None)
    assert ok is True
    assert settings.GRID_TOGGLE not in d.taps


def test_auto_battle_not_off_refuses_and_escapes():
    d = _Driver([_settings_frame(grid_on=False, auto_off=False)])
    ok = settings.set_battle_grid(d.capture, d.tap, True, sleep=lambda s: None)
    assert ok is False
    assert settings.GRID_TOGGLE not in d.taps
    assert d.taps[-2:] == [settings.SETTINGS_CLOSE, settings.BATTLE_MENU_CLOSE]


def test_unrecognized_page_fails_soft():
    d = _Driver([np.zeros((1080, 2340, 3), np.uint8)])
    ok = settings.set_battle_grid(d.capture, d.tap, True, sleep=lambda s: None)
    assert ok is False
    assert settings.GRID_TOGGLE not in d.taps


def test_snap_to_lattice_brackets_and_passthrough():
    lattice = ((600, 728, 856), (300, 420, 540))
    assert vision.snap_to_lattice((700, 350), lattice) == (664.0, 360.0)
    # outside the detected span keeps the raw coordinate on that axis
    assert vision.snap_to_lattice((100, 350), lattice) == (100, 360.0)
    assert vision.snap_to_lattice((700, 900), lattice) == (664.0, 900)
