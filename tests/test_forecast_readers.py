"""Semantic contract of the M2 game-forecast readers.

Accuracy on real captures is pinned by tests/fixtures/vision/forecast/;
these tests cover reader semantics that need no screenshots: declining on
frames without the screen anchor, and name-signature behavior.
"""

from __future__ import annotations

import cv2
import numpy as np

from ggge_ai.battle import vision
from ggge_ai.content.stage_def import signature_distance


def _blank_frame() -> np.ndarray:
    return np.zeros((1080, 2340, 3), np.uint8)


def _text_frame(text: str, origin: tuple[int, int] = (600, 160)) -> np.ndarray:
    frame = _blank_frame()
    cv2.putText(frame, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    return frame


def test_readers_decline_without_anchor() -> None:
    frame = _blank_frame()
    assert vision.read_weapon_select_forecast(frame) is None
    assert vision.read_battle_prep_forecast(frame) is None
    assert vision.read_enemy_summary(frame) is None
    assert vision.read_kill_counter(frame) is None
    assert vision.is_battle_prep_reaction(frame) is False
    assert vision.read_reaction_stance_menu(frame) is None
    assert vision.read_avatar_hits(frame) == ()
    assert vision.has_support_defense_label(frame) is False


def test_initiator_hit_selection() -> None:
    """-應戰- takes the red (enemy) hit; -攻擊- the rightmost blue: supports
    sit left of our main attack and the enemy counter right of it."""
    hits = (
        vision.AvatarHit(x=963, pct=85, faction="ally"),
        vision.AvatarHit(x=1162, pct=100, faction="ally"),
        vision.AvatarHit(x=1363, pct=55, faction="enemy"),
    )
    assert vision._initiator_hit(hits, is_reaction=False) == 100
    assert vision._initiator_hit(hits, is_reaction=True) == 55
    assert vision._initiator_hit((), is_reaction=True) is None
    unknown = (vision.AvatarHit(x=863, pct=90, faction=None),)
    assert vision._initiator_hit(unknown, is_reaction=False) is None


def test_defender_avatar_slot_arithmetic() -> None:
    """The stance-menu entry point is derived, not detected: row centered on
    963, pitch 200, avatar count = tokens + labelled interceptor + maybe the
    defender itself, disambiguated by the row-centering parity."""

    def hit(x: int, faction: str) -> vision.AvatarHit:
        return vision.AvatarHit(x=x, pct=100, faction=faction)

    two = (hit(863, "enemy"), hit(1063, "ally"))
    assert vision.defender_avatar_slot(two, False) == (1063, 938)
    # defender in dodge stance carries no pct; parity still lands the slot
    assert vision.defender_avatar_slot((hit(863, "enemy"),), False) == (1063, 938)
    # the interceptor has no pct either -- the support-defense label counts it
    supdef = (hit(763, "enemy"), hit(1163, "ally"))
    assert vision.defender_avatar_slot(supdef, True) == (1163, 938)
    # first-strike layout: our support, the enemy, the interceptor, us = 4
    strike = (hit(663, "ally"), hit(863, "enemy"))
    assert vision.defender_avatar_slot(strike, True) == (1263, 938)
    assert vision.defender_avatar_slot((), False) is None
    # an off-grid token is a layout surprise, never a guess
    assert vision.defender_avatar_slot((hit(900, "enemy"),), False) is None
    # tokens with conflicting parity cannot come from one centered row
    mixed = (hit(863, "enemy"), hit(963, "ally"))
    assert vision.defender_avatar_slot(mixed, False) is None


def test_available_stances_ordering() -> None:
    dodge = vision.StanceOption(stance="dodge", tap=(1540, 940), enabled=True)
    guard = vision.StanceOption(stance="shield", tap=(1352, 940), enabled=True)
    dead = vision.StanceOption(
        stance="counter", tap=(1165, 940), enabled=False, weapon_index=0
    )
    live_w = vision.StanceOption(
        stance="counter", tap=(978, 940), enabled=True, weapon_index=1
    )
    menu = vision.ReactionStanceMenu(dodge=dodge, guard=guard, counters=(dead, live_w))
    assert menu.available_stances == ("dodge", "shield", "counter")
    disarmed = vision.ReactionStanceMenu(dodge=dodge, guard=None, counters=(dead,))
    assert disarmed.available_stances == ("dodge",)


def test_signature_distance_semantics() -> None:
    sig = vision.name_signature(_text_frame("GUNDAM"), vision.FORECAST_LEFT_NAME_REGION)
    assert sig is not None
    assert signature_distance(sig, sig) == 0
    assert signature_distance(None, sig) == 64
    assert signature_distance(sig, None) == 64
    assert signature_distance(None, None) == 64


def test_signature_is_shift_invariant_and_discriminative() -> None:
    base = vision.name_signature(_text_frame("GUNDAM"), vision.FORECAST_LEFT_NAME_REGION)
    shifted = vision.name_signature(
        _text_frame("GUNDAM", origin=(604, 157)), vision.FORECAST_LEFT_NAME_REGION
    )
    other = vision.name_signature(_text_frame("ZAKU II"), vision.FORECAST_LEFT_NAME_REGION)
    assert signature_distance(base, shifted) <= 4
    assert signature_distance(base, other) > 10


def test_signature_none_on_empty_band() -> None:
    assert vision.name_signature(_blank_frame(), vision.FORECAST_LEFT_NAME_REGION) is None
