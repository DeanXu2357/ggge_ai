"""Pixel-level helpers for the manual battle controller.

All coordinates are in the 2340x1080 landscape reference frame.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

STORY_MENU_TEMPLATE = (
    Path(__file__).resolve().parents[3] / "assets" / "templates" / "screens" / "story.png"
)

DIALOG_CURSOR_TEMPLATE = (
    Path(__file__).resolve().parents[3] / "assets" / "templates" / "elements" / "dialog_cursor.png"
)

DEFEAT_SCREEN_TEMPLATE = (
    Path(__file__).resolve().parents[3] / "assets" / "templates" / "screens" / "battle_failed.png"
)

# the FAILED banner sits top-center; restrict the match there so a high
# TM_CCOEFF response cannot come from a darkened battle overlay elsewhere
DEFEAT_SCREEN_REGION = (980, 0, 400, 175)

# a dying unit pops an inline line of dialogue with a cyan ▼ advance cursor
# that slides horizontally with the line length, so it must be matched free
# of a fixed column. it lives in the bottom text band; the right edge runs
# past x=1900 because a short line parks the cursor near the frame edge
DIALOG_CURSOR_REGION = (480, 800, 1620, 130)

ATTACK_BUTTON_BOX = (1990, 900, 240, 160)
UNIT_CARD_STRIP_BOX = (170, 840, 900, 200)
# one actable-unit card spans roughly a fifth of the strip; scan with a
# window this wide to score the brightest local card block, not the whole strip
UNIT_CARD_WINDOW = 180
FIRST_UNIT_CARD = (300, 930)

# map area free of HUD overlays, used when scanning for cells / units.
# bottom capped above the MP/skill/support button row (y>=880) so their
# bright circular rims are never mistaken for movable cells
MAP_REGION = (150, 250, 1600, 620)

# wider scan for unit HP arcs: units drift into the strip above MAP_REGION
# (below the turn banner); the right edge stops short of the unit info
# panel whose EN bar is a wide flat orange strip
UNIT_SCAN_REGION = (150, 90, 1510, 780)

# on the our-turn hub the actable-unit card strip (bright portraits with
# HP bars) fills the bottom, so scouting there must stop above it
HUB_SCAN_REGION = (150, 90, 1510, 700)


def _crop(frame: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    x, y, w, h = box
    return frame[y : y + h, x : x + w]


def attack_enabled(frame: np.ndarray) -> bool:
    """The attack button ring is saturated blue when a target is locked,
    near-black when the selected weapon is out of range (射程外)."""
    hsv = cv2.cvtColor(_crop(frame, ATTACK_BUTTON_BOX), cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    blue = (h > 90) & (h < 130) & (s > 80) & (v > 80)
    return float(blue.mean()) > 0.3


def unit_cards_present(frame: np.ndarray) -> bool:
    """Actable-unit cards render as bright framed portraits above a blue
    HP bar. A lone remaining card lights only about a fifth of the strip,
    so a whole-strip brightness mean sinks under any empty-strip guard and
    the last unit is never picked (10+ forced-standby turns to death, the
    20260705 HARD-2 loss). Slide a card-width window across the strip and
    test the brightest local block instead: measured on those captures a
    single card peaks at ~0.30 local bright fraction and seven cards at
    ~0.58, while an idle strip or between-phase animation stays <=0.14."""
    hsv = cv2.cvtColor(_crop(frame, UNIT_CARD_STRIP_BOX), cv2.COLOR_BGR2HSV)
    bright = (hsv[..., 2] > 140).astype(np.float64)
    win = UNIT_CARD_WINDOW
    if bright.shape[1] <= win:
        return float(bright.mean()) > 0.2
    prefix = np.concatenate(([0.0], np.cumsum(bright.sum(axis=0))))
    window_bright = prefix[win:] - prefix[:-win]
    peak = float(window_bright.max()) / (win * bright.shape[0])
    return peak > 0.2


def find_threat_cells(frame: np.ndarray) -> list[tuple[int, int]]:
    """Movable cells inside enemy attack range carry a translucent red fill
    with a red "!" marker. Their centroid points toward the enemy force."""
    x0, y0, w, h = MAP_REGION
    hsv = cv2.cvtColor(_crop(frame, MAP_REGION), cv2.COLOR_BGR2HSV)
    red = cv2.inRange(hsv, (0, 90, 60), (10, 255, 255)) | cv2.inRange(
        hsv, (170, 90, 60), (180, 255, 255)
    )
    red = cv2.morphologyEx(red, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    n, _, stats, cents = cv2.connectedComponentsWithStats(red)
    out = []
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        bw = stats[i, cv2.CC_STAT_WIDTH]
        bh = stats[i, cv2.CC_STAT_HEIGHT]
        # one grid cell is ~90px; accept cell-sized red patches only, so
        # solid range overlays and unit bodies are ignored
        if 400 <= area <= 6000 and bw < 140 and bh < 140:
            out.append((x0 + int(cents[i][0]), y0 + int(cents[i][1])))
    return out


def find_move_cells(frame: np.ndarray) -> list[tuple[int, int]]:
    """Reachable cells are drawn as bright white rounded-square outlines."""
    x0, y0, w, h = MAP_REGION
    hsv = cv2.cvtColor(_crop(frame, MAP_REGION), cv2.COLOR_BGR2HSV)
    white = cv2.inRange(hsv, (0, 0, 180), (180, 60, 255))
    white = cv2.morphologyEx(white, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in contours:
        bx, by, bw, bh = cv2.boundingRect(c)
        if 55 <= bw <= 130 and 55 <= bh <= 130:
            out.append((x0 + bx + bw // 2, y0 + by + bh // 2))
    return out


def _ring_blobs(mask: np.ndarray, region: tuple[int, int, int, int]) -> list[tuple[int, int]]:
    """HP arcs render as wide flat ellipse arcs at a unit's feet; the
    aspect filter rejects unit bodies, threat "!" marks and shield icons.
    The lower width bound stays small because the colored part of the arc
    shrinks as the unit takes damage.

    Two extra shape gates keep body/shield paint of the matching color out
    (measured on 20260705 HARD-2 captures): a real arc is a thin band whose
    height stays in [12, 32] (clean arcs measure bh 16-24; merged body+arc
    blobs run bh 45-60), and a solid stroke whose filled fraction is >= 0.35
    (arcs measure 0.39-0.47; sparse body fragments and shields measure
    0.19-0.33)."""
    x0, y0 = region[0], region[1]
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, _, stats, cents = cv2.connectedComponentsWithStats(mask)
    out = []
    for i in range(1, n):
        bw = stats[i, cv2.CC_STAT_WIDTH]
        bh = stats[i, cv2.CC_STAT_HEIGHT]
        area = stats[i, cv2.CC_STAT_AREA]
        if (
            35 <= bw <= 160
            and 12 <= bh <= 32
            and bw / bh >= 1.6
            and area >= 120
            and area / (bw * bh) >= 0.35
        ):
            out.append((x0 + int(cents[i][0]), y0 + int(cents[i][1])))
    return out


def _dedupe(points: list[tuple[int, int]], radius: int = 70) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for p in points:
        for i, q in enumerate(merged):
            if (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 < radius * radius:
                merged[i] = ((p[0] + q[0]) // 2, (p[1] + q[1]) // 2)
                break
        else:
            merged.append(p)
    return merged


# the arc under every unit is its HP bar and its color encodes the faction:
# red = enemy, teal = third party (not controllable), blue = our own units.
# arcs glow but are not fully saturated (S<=210, V>=155), which separates
# them from unit-body paint (darker) and HUD bars (fully saturated).
# every arc, regardless of faction, is a two-tone gradient: a faction-color
# left half plus a SHARED orange/yellow right half (measured hue ~14 on
# 20260705-170520.png at orig (1050,607)). the enemy hue must stop below
# that shared orange or every ally/third-party arc trips as a false enemy:
# true enemy red measures hue ~8 (same capture, orig (985,600)), so the band
# ends at 10. widening it back to 25 is what made an all-ally PHASE START
# frame (20260705-165933.png) report five phantom enemies.
def find_enemy_units(
    frame: np.ndarray, region: tuple[int, int, int, int] = UNIT_SCAN_REGION
) -> list[tuple[int, int]]:
    hsv = cv2.cvtColor(_crop(frame, region), cv2.COLOR_BGR2HSV)
    red = cv2.inRange(hsv, (0, 100, 155), (10, 210, 255)) | cv2.inRange(
        hsv, (168, 100, 155), (180, 210, 255)
    )
    return _dedupe(_ring_blobs(red, region))


def find_ally_units(
    frame: np.ndarray, region: tuple[int, int, int, int] = UNIT_SCAN_REGION
) -> list[tuple[int, int]]:
    hsv = cv2.cvtColor(_crop(frame, region), cv2.COLOR_BGR2HSV)
    blue = cv2.inRange(hsv, (100, 100, 155), (125, 210, 255))
    return _dedupe(_ring_blobs(blue, region))


def find_third_party_units(
    frame: np.ndarray, region: tuple[int, int, int, int] = UNIT_SCAN_REGION
) -> list[tuple[int, int]]:
    hsv = cv2.cvtColor(_crop(frame, region), cv2.COLOR_BGR2HSV)
    teal = cv2.inRange(hsv, (78, 100, 155), (97, 210, 255))
    return _dedupe(_ring_blobs(teal, region))


def measure_camera_shift(
    prev: np.ndarray,
    cur: np.ndarray,
    region: tuple[int, int, int, int] = MAP_REGION,
) -> tuple[tuple[float, float], float]:
    """How far the camera moved between two frames, in screen pixels,
    with the phase-correlation response as confidence (near 0 on
    featureless views like open space). Camera shift is the negation of
    the content shift: panning east makes the terrain slide west."""
    a = cv2.cvtColor(_crop(prev, region), cv2.COLOR_BGR2GRAY).astype(np.float32)
    b = cv2.cvtColor(_crop(cur, region), cv2.COLOR_BGR2GRAY).astype(np.float32)
    window = cv2.createHanningWindow((a.shape[1], a.shape[0]), cv2.CV_32F)
    (sx, sy), response = cv2.phaseCorrelate(a, b, window)
    return (-sx, -sy), response


def locate_story_menu(frame: np.ndarray, threshold: float = 0.6) -> tuple[int, int] | None:
    """Find the story MENU button wherever it sits: mid-battle stories add
    a ☰ button that shifts MENU left of its pre-battle position."""
    template = cv2.imread(str(STORY_MENU_TEMPLATE))
    if template is None:
        return None
    result = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(result)
    if score < threshold:
        return None
    h, w = template.shape[:2]
    return (loc[0] + w // 2, loc[1] + h // 2)


def locate_dialog_cursor(frame: np.ndarray, threshold: float = 0.85) -> tuple[int, int] | None:
    """Find the cyan ▼ advance cursor of an in-battle death/defeat line.
    Free-position match within the bottom text band because the cursor tracks
    the end of the line; returns its center or None. Threshold picked from the
    gap between positive frames (>=0.95) and non-dialog frames (<=0.70)."""
    template = cv2.imread(str(DIALOG_CURSOR_TEMPLATE))
    if template is None:
        return None
    x0, y0, w, h = DIALOG_CURSOR_REGION
    band = frame[y0 : y0 + h, x0 : x0 + w]
    if band.shape[0] < h or band.shape[1] < w:
        return None
    result = cv2.matchTemplate(band, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(result)
    if score < threshold:
        return None
    th, tw = template.shape[:2]
    return (x0 + loc[0] + tw // 2, y0 + loc[1] + th // 2)


def is_defeat_screen(frame: np.ndarray, threshold: float = 0.6) -> bool:
    """True on the post-battle FAILED screen (our whole force wiped out).
    Matches the top-center FAILED banner within DEFEAT_SCREEN_REGION;
    measured scores are ~1.0 on the three 20260705 defeat frames and <=0.18
    on hub / weapon / phase-start / animation frames, so the 0.6 gate sits
    in a wide empty gap well clear of TM_CCOEFF darkened-overlay matches."""
    template = cv2.imread(str(DEFEAT_SCREEN_TEMPLATE))
    if template is None:
        return False
    x0, y0, w, h = DEFEAT_SCREEN_REGION
    band = frame[y0 : y0 + h, x0 : x0 + w]
    if band.shape[0] < template.shape[0] or band.shape[1] < template.shape[1]:
        return False
    result = cv2.matchTemplate(band, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, _ = cv2.minMaxLoc(result)
    return score >= threshold


def nearest_point(points: list[tuple[int, int]], target: tuple[int, int]) -> tuple[int, int] | None:
    if not points:
        return None
    tx, ty = target
    return min(points, key=lambda p: (p[0] - tx) ** 2 + (p[1] - ty) ** 2)


def centroid(points: list[tuple[int, int]]) -> tuple[int, int] | None:
    if not points:
        return None
    xs, ys = zip(*points)
    return (sum(xs) // len(points), sum(ys) // len(points))
