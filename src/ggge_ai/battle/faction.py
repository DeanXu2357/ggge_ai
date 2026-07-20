"""Faction identification for the phase-2 identify pass (#26 定案 5).

The scan produces a factionless unit pool; faction comes from tapping a
unit and reading WHERE its summary banner docks -- left = enemy, right =
ally (the user's settled reading of the card-side mystery; arc colors
are demoted to existence signals and never decide faction). The seam is
a Protocol so the survey loop stays independent of the evidence channel:
the dock reader is the authority, and a turn-1 cobalt-ring + white-VV
assist can join later as another implementation without touching the
loop. No verdict is ever guessed -- an unreadable or ambiguous banner
returns None and the caller decides how loudly to fail.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from . import vision
from .state import Faction

log = logging.getLogger(__name__)

# the left-dock anchor region is the summary reader's calibrated gate;
# the right-dock (ally) region is pending calibration -- no live sample
# of an ally banner has been measured yet, so the channel ships disabled
# and identify() cannot produce an ALLY verdict until it is filled in
LEFT_DOCK_REGION = vision.ENEMY_SUMMARY_ANCHOR_REGION
RIGHT_DOCK_REGION: tuple[int, int, int, int] | None = None
DOCK_SCORE_THRESHOLD = vision.ENEMY_SUMMARY_ANCHOR_THRESHOLD


@dataclass(frozen=True)
class FactionVerdict:
    """One identified unit: the faction, the dock side that proved it and
    the anchor score behind the call."""

    faction: Faction
    side: str
    score: float


class FactionIdentifier(Protocol):
    """Evidence seam of the identify pass: the frame shows a unit's
    summary banner (the survey tapped the unit and waited for the card);
    the identifier reads faction off it. None = no banner readable, or
    conflicting evidence -- never a guess."""

    def identify(self, frame: np.ndarray) -> FactionVerdict | None: ...


@dataclass
class DockBannerIdentifier:
    """The authoritative implementation: score the HP-label anchor in
    both dock regions, the side that carries it is the faction. A right
    region of None keeps that channel off until it is calibrated; both
    sides scoring is a contradiction and yields None, loudly."""

    left_region: tuple[int, int, int, int] = LEFT_DOCK_REGION
    right_region: tuple[int, int, int, int] | None = RIGHT_DOCK_REGION
    threshold: float = DOCK_SCORE_THRESHOLD

    def identify(self, frame: np.ndarray) -> FactionVerdict | None:
        left = vision.summary_anchor_score(frame, self.left_region)
        right = (
            vision.summary_anchor_score(frame, self.right_region)
            if self.right_region is not None
            else 0.0
        )
        left_hit = left >= self.threshold
        right_hit = right >= self.threshold
        if left_hit and right_hit:
            log.warning(
                "banner anchor scores on BOTH docks (left %.3f / right %.3f); "
                "refusing a faction verdict",
                left,
                right,
            )
            return None
        if left_hit:
            return FactionVerdict(faction=Faction.ENEMY, side="left", score=left)
        if right_hit:
            return FactionVerdict(faction=Faction.ALLY, side="right", score=right)
        return None
