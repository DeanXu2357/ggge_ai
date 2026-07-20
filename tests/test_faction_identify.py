"""DockBannerIdentifier (#26 定案 5): faction = which side the summary
banner docks on. Left dock rides the real calibrated fixture; the right
dock's MECHANISM is exercised by translating that same card to a
right-side region -- the real right-dock region constant is content and
arrives with its own calibrated sample."""

from pathlib import Path

import cv2
import numpy as np

from ggge_ai.battle.faction import DockBannerIdentifier
from ggge_ai.battle.state import Faction

FIXTURES = Path(__file__).parent / "fixtures" / "vision"

CARD_W = 1000
RIGHT_SHIFT = 650


def _hub_canvas() -> np.ndarray:
    crop = cv2.imread(str(FIXTURES / "forecast" / "hub_summary_top.png"))
    assert crop is not None
    canvas = np.zeros((1080, 2340, 3), np.uint8)
    canvas[0 : crop.shape[0], 0 : crop.shape[1]] = crop
    return canvas


def _right_dock_canvas() -> np.ndarray:
    left = _hub_canvas()
    canvas = np.zeros_like(left)
    card = left[0:300, 0:CARD_W]
    canvas[0:300, RIGHT_SHIFT : RIGHT_SHIFT + CARD_W] = card
    return canvas


def _right_region() -> tuple[int, int, int, int]:
    x, y, w, h = DockBannerIdentifier().left_region
    return (x + RIGHT_SHIFT, y, w, h)


def test_left_dock_is_an_enemy_verdict():
    verdict = DockBannerIdentifier().identify(_hub_canvas())
    assert verdict is not None
    assert verdict.faction is Faction.ENEMY
    assert verdict.side == "left"
    assert verdict.score >= DockBannerIdentifier().threshold


def test_right_dock_is_an_ally_verdict():
    ident = DockBannerIdentifier(right_region=_right_region())
    verdict = ident.identify(_right_dock_canvas())
    assert verdict is not None
    assert verdict.faction is Faction.ALLY
    assert verdict.side == "right"


def test_uncalibrated_right_channel_stays_silent():
    verdict = DockBannerIdentifier().identify(_right_dock_canvas())
    assert verdict is None


def test_no_banner_yields_no_verdict():
    ident = DockBannerIdentifier(right_region=_right_region())
    assert ident.identify(np.zeros((1080, 2340, 3), np.uint8)) is None


def test_both_docks_scoring_is_a_contradiction_not_a_guess():
    left = _hub_canvas()
    both = left.copy()
    both[0:300, RIGHT_SHIFT : RIGHT_SHIFT + CARD_W] = left[0:300, 0:CARD_W]
    ident = DockBannerIdentifier(right_region=_right_region())
    assert ident.identify(both) is None
