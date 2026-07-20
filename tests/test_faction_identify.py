"""DockBannerIdentifier (#26 定案 5): faction = which side the summary
banner docks on. Left dock rides the calibrated hub fixture; the right
dock rides the 20260714 HARD-1 archive frame that settled the +818
translation. The both-docks frame (battle-prep forecast band, where the
right panel shares the summary geometry) must be refused, never guessed
-- that shared geometry is exactly why a lone right hit proves nothing
outside hub context."""

from pathlib import Path

import cv2
import numpy as np

from ggge_ai.battle.faction import RIGHT_DOCK_SHIFT, DockBannerIdentifier
from ggge_ai.battle.state import Faction

FIXTURES = Path(__file__).parent / "fixtures" / "vision"

CARD_W = 1000


def _band_canvas(name: str) -> np.ndarray:
    crop = cv2.imread(str(FIXTURES / name))
    assert crop is not None
    canvas = np.zeros((1080, 2340, 3), np.uint8)
    canvas[0 : crop.shape[0], 0 : crop.shape[1]] = crop
    return canvas


def test_left_dock_is_an_enemy_verdict():
    verdict = DockBannerIdentifier().identify(
        _band_canvas("forecast/hub_summary_top.png")
    )
    assert verdict is not None
    assert verdict.faction is Faction.ENEMY
    assert verdict.side == "left"
    assert verdict.score >= DockBannerIdentifier().threshold


def test_right_dock_is_an_ally_verdict():
    verdict = DockBannerIdentifier().identify(
        _band_canvas("faction/right_dock_hard1_20260714.png")
    )
    assert verdict is not None
    assert verdict.faction is Faction.ALLY
    assert verdict.side == "right"
    assert verdict.score >= DockBannerIdentifier().threshold


def test_translated_left_card_hits_the_right_region():
    """The +818 translation is the calibration's load-bearing claim: a
    left card shifted by exactly that lands in the default right region."""
    left = _band_canvas("forecast/hub_summary_top.png")
    canvas = np.zeros_like(left)
    canvas[0:300, RIGHT_DOCK_SHIFT : RIGHT_DOCK_SHIFT + CARD_W] = left[
        0:300, 0:CARD_W
    ]
    verdict = DockBannerIdentifier().identify(canvas)
    assert verdict is not None
    assert verdict.faction is Faction.ALLY


def test_disabled_right_channel_stays_silent():
    ident = DockBannerIdentifier(right_region=None)
    assert ident.identify(_band_canvas("faction/right_dock_hard1_20260714.png")) is None


def test_no_banner_yields_no_verdict():
    assert DockBannerIdentifier().identify(np.zeros((1080, 2340, 3), np.uint8)) is None


def test_both_docks_scoring_is_a_contradiction_not_a_guess():
    verdict = DockBannerIdentifier().identify(
        _band_canvas("faction/both_docks_forecast_20260719.png")
    )
    assert verdict is None
