"""Pixel-level helpers for the manual battle controller.

All coordinates are in the 2340x1080 landscape reference frame.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from ..sim import DefenseKind
from ..vision import digits
from ..vision.template import PREPROCESSORS

_highpass = PREPROCESSORS["highpass"]


@lru_cache(maxsize=16)
def _cached_template(path_str: str) -> np.ndarray | None:
    """cv2.imread with memoization: templates read on hot controller-loop
    paths (modal / faction checks) should not touch disk every frame."""
    return cv2.imread(path_str)


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

HIDDEN_BATTLE_WARNING_TEMPLATE = (
    Path(__file__).resolve().parents[3]
    / "assets"
    / "templates"
    / "screens"
    / "hidden_battle_warning.png"
)

# the hidden-battle WARNING banner + 不明機體出現 subtitle sit top-center;
# restrict the match there so a high TM_CCOEFF response cannot come from the
# darkened battle overlay the modal dims behind itself
HIDDEN_BATTLE_WARNING_REGION = (990, 22, 380, 230)

UNIT_DETAIL_MODAL_TEMPLATE = (
    Path(__file__).resolve().parents[3]
    / "assets"
    / "templates"
    / "elements"
    / "unit_detail_modal.png"
)

# the 單位設置詳情 title sits top-center of the unit-setup detail modal and is
# identical across its 組合資訊 / 武裝技能 / 能力OP tabs, so it is a stable modal
# anchor. a stray keyguard drag onto a live map opens this modal on top of an
# enemy unit; matching the title band (not the dimmed map behind it) detects it
# so the controller can escape. measured 1.0 on the four 20260706 modal
# captures and <=0.24 on stage_info / hub / menu frames, so 0.6 is a wide gap.
UNIT_DETAIL_MODAL_REGION = (1000, 50, 380, 100)

# the our-turn banner prints "TURN <n>" top-left; this box isolates the first
# digit so its glyph repaint is measurable. the same turn redraws the digit
# identically (self-correlation ~1.0) while a new turn draws a different glyph,
# which lets the controller veto phantom turn increments (a stalled modal used
# to inflate the internal turn counter past the on-screen TURN number).
TURN_MARKER_REGION = (260, 78, 40, 36)

# the full TURN number (digits after the TURN label, black on the white
# chip): read via template-digit OCR. wide enough for two digits; the
# label text ends around x=230 on every calibrated capture
TURN_NUMBER_REGION = (234, 62, 96, 42)
TURN_DIGIT_HEIGHT = 28

# a dying unit pops an inline line of dialogue with a cyan ▼ advance cursor
# that slides horizontally with the line length, so it must be matched free
# of a fixed column. it lives in the bottom text band; the right edge runs
# past x=1900 because a short line parks the cursor near the frame edge.
# band is tall enough for both layouts: the inline death line parks the
# cursor around y 840-870, the two-row story dialog (portrait + speaker
# banner) around y 905-925 -- the old 130px band ended at y=930 and the
# 38px template could not reach a cursor starting at 905 (2026-07-11
# live stall, whole-frame score 0.945)
DIALOG_CURSOR_REGION = (480, 800, 1620, 170)

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
    ~0.58, while an idle strip or between-phase animation stays <=0.14.

    A unit-setup detail modal (opened by a stray keyguard drag) fills the
    strip band with a bright light-grey panel and trips the brightness gate
    (measured True on all four 20260706 modal captures). Reject it first so
    the controller never mistakes an open modal for an actable-unit hub."""
    if is_unit_detail_modal(frame):
        return False
    hsv = cv2.cvtColor(_crop(frame, UNIT_CARD_STRIP_BOX), cv2.COLOR_BGR2HSV)
    bright = (hsv[..., 2] > 140).astype(np.float64)
    win = UNIT_CARD_WINDOW
    if bright.shape[1] <= win:
        return float(bright.mean()) > 0.2
    prefix = np.concatenate(([0.0], np.cumsum(bright.sum(axis=0))))
    window_bright = prefix[win:] - prefix[:-win]
    peak = float(window_bright.max()) / (win * bright.shape[0])
    return peak > 0.2


UNIT_CARD_COUNT_REGION = (170, 840, 2000, 200)
UNIT_CARD_BAR_ROW_BAND = (140, 186)
UNIT_CARD_BAR_WIDTH = (12, 170)


def count_unit_cards(frame: np.ndarray) -> int:
    """How many actable-unit cards the strip shows (the user-settled
    authority for "which units are ours and can act": at turn start the
    count equals living allies, then it drops as units act and can bump
    back up when a kill re-activation returns a card).

    Counting keys on the blue HP bar at each card's foot, not on strip
    brightness: bright map terrain behind the band defeats any brightness
    profile (all-bright strip on the 20260713-225448 corpus), while the
    bars sit on a fixed ~175px pitch at a stable row (measured 159 on
    20260705/06 PNG hubs, 163-167 on corpus JPEGs). A bar's width is the
    unit's HP fraction -- damaged units measured 92/66/18px -- so bars are
    counted by presence above a 12px floor, not by full width; a nearly
    dead unit under that floor undercounts by one until the next read.
    The [12, 170] width band rejects the PHASE START banner (an 836px+
    blue beam through the same rows), and the row band rejects blue UI
    outside the bar line. Ground truth: subagent visual count 7/6/10/0
    on the four fixture sources (2026-07-14)."""
    x0, y0, w, h = UNIT_CARD_COUNT_REGION
    hsv = cv2.cvtColor(_crop(frame, UNIT_CARD_COUNT_REGION), cv2.COLOR_BGR2HSV)
    hue, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    blue = (hue > 95) & (hue < 130) & (s > 100) & (v > 120)
    if not blue.any():
        return 0
    bar_row = int(blue.sum(axis=1).argmax())
    lo, hi = UNIT_CARD_BAR_ROW_BAND
    if not lo <= bar_row <= hi:
        return 0
    band = blue[max(0, bar_row - 6) : bar_row + 7]
    cols = band.mean(axis=0) > 0.5
    min_w, max_w = UNIT_CARD_BAR_WIDTH
    count = 0
    run = 0
    for on in cols:
        if on:
            run += 1
        else:
            if min_w <= run <= max_w:
                count += 1
            run = 0
    if min_w <= run <= max_w:
        count += 1
    return count


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


# the 顯示方格 in-battle grid (#25): vertical lines ride a stable ~128px
# pitch while horizontal spacings grow down-screen (108->123 measured on the
# 20260719 event stage -- mild vertical perspective), so the lattice is
# reported as raw line positions, never a single cell size. The lattice
# serves pan-measurement texture, map-bounds work and (future) cell
# assignment; observations themselves stay raw -- rewriting them to cell
# centers broke every gridless consumer's 60px match gates (20260719 runs
# 4/5), so snap_to_lattice is kept for cell math, not applied to the map.
# bottom stops at y780: the 請選擇欲行動的單位 prompt band's top edge reads
# as a phantom row line at y~823, and HUB_SCAN_REGION only yields arcs above
# y790 anyway
GRID_LATTICE_REGION = (150, 250, 1600, 530)
GRID_LINE_MIN_SPACING = 90
GRID_LINE_MAX_SPACING = 160
# a real grid fills the region: ~12 columns at the measured 128px pitch and
# ~5 rows in the 530px band. Sparse pseudo-lines (unit sprites on a
# gridless frame lined up by chance) never reach these counts
GRID_MIN_COLS = 6
GRID_MIN_ROWS = 4
# real-lattice gap spread stays tight (max-min <= 26 measured with the mild
# vertical perspective); the unit-move blue-cell overlay traces the same
# grid but its detected edges wobble across half-cells (spread 50+), too
# sloppy to snap against
GRID_GAP_RANGE = 35


def read_grid_lattice(
    frame: np.ndarray,
) -> tuple[tuple[int, ...], tuple[int, ...]] | None:
    """Gridline positions (column xs, row ys) in full-frame pixels, or None
    when no plausible lattice is on screen. Highpass projections: gridlines
    are thin brightness ridges spanning the whole map, so their |highpass|
    column/row means peak while units and map art average out."""
    x0, y0, w, h = GRID_LATTICE_REGION
    crop = _crop(frame, GRID_LATTICE_REGION)
    if crop.shape[0] < h or crop.shape[1] < w:
        return None
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)
    hp = np.abs(gray - cv2.GaussianBlur(gray, (0, 0), 6))

    def lines(profile: np.ndarray, offset: int) -> list[int]:
        prof = profile - profile.mean()
        gate = prof.std() * 1.2
        out: list[int] = []
        for i in range(2, len(prof) - 2):
            if prof[i] >= prof[i - 1] and prof[i] >= prof[i + 1] and prof[i] > gate:
                if not out or i - (out[-1] - offset) >= GRID_LINE_MIN_SPACING:
                    out.append(offset + i)
                elif prof[i] > prof[out[-1] - offset]:
                    out[-1] = offset + i
        return out

    def trim(positions: list[int]) -> list[int]:
        """Boundary lines whose gap to their neighbor falls outside the
        cell band are screen furniture (a panel edge), not grid."""
        out = list(positions)
        while len(out) >= 2 and not (
            GRID_LINE_MIN_SPACING <= out[1] - out[0] <= GRID_LINE_MAX_SPACING
        ):
            out.pop(0)
        while len(out) >= 2 and not (
            GRID_LINE_MIN_SPACING <= out[-1] - out[-2] <= GRID_LINE_MAX_SPACING
        ):
            out.pop()
        return out

    cols = trim(lines(hp.mean(axis=0), x0))
    rows = trim(lines(hp.mean(axis=1), y0))

    def plausible(positions: list[int], min_lines: int) -> bool:
        if len(positions) < min_lines:
            return False
        gaps = [b - a for a, b in zip(positions, positions[1:])]
        if max(gaps) - min(gaps) > GRID_GAP_RANGE:
            return False
        return all(
            GRID_LINE_MIN_SPACING <= g <= GRID_LINE_MAX_SPACING for g in gaps
        )

    if not plausible(cols, GRID_MIN_COLS) or not plausible(rows, GRID_MIN_ROWS):
        return None
    return tuple(cols), tuple(rows)


def snap_to_lattice(
    point: tuple[float, float],
    lattice: tuple[tuple[int, ...], tuple[int, ...]],
) -> tuple[float, float]:
    """Nearest cell center for a screen point: the midpoint of its
    bracketing gridline pair per axis. Points outside the detected line
    span keep their original coordinate on that axis."""

    def snap(v: float, positions: tuple[int, ...]) -> float:
        if v < positions[0] or v > positions[-1]:
            return v
        for a, b in zip(positions, positions[1:]):
            if a <= v <= b:
                return (a + b) / 2.0
        return v

    cols, rows = lattice
    return (snap(point[0], cols), snap(point[1], rows))


def measure_arc_shift(
    prev: np.ndarray, cur: np.ndarray, *, tolerance: int = 24
) -> tuple[float, float] | None:
    """Camera shift from HP-arc constellations: every arc pair between the
    two frames votes for a translation, and a mode supported by at least
    two arcs wins. Second modality for #24: phase correlation goes blind
    (response < 0.05) on featureless star fields and on frames where a
    swipe triggered a non-translational UI change -- blindly trusting the
    gesture there displaced whole scan rows (the 20260719 west-edge ghost
    coordinates). None without a consensus; faction does not matter, so
    the hub pink-ally ambiguity cannot corrupt the vote."""

    def arcs(frame: np.ndarray) -> list[tuple[int, int]]:
        return (
            find_enemy_units(frame, region=HUB_SCAN_REGION)
            + find_ally_units(frame, region=HUB_SCAN_REGION)
            + find_third_party_units(frame, region=HUB_SCAN_REGION)
        )

    a, b = arcs(prev), arcs(cur)
    if len(a) < 2 or len(b) < 2:
        return None
    votes: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for ax, ay in a:
        for bx, by in b:
            d = (ax - bx, ay - by)
            key = (round(d[0] / tolerance), round(d[1] / tolerance))
            votes.setdefault(key, []).append((float(d[0]), float(d[1])))
    best = max(votes.values(), key=len)
    if len(best) < 2:
        return None
    second = sorted((len(v) for v in votes.values()), reverse=True)
    if len(second) > 1 and second[1] == second[0]:
        return None
    return (
        sum(d[0] for d in best) / len(best),
        sum(d[1] for d in best) / len(best),
    )


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


def is_hidden_battle_warning(frame: np.ndarray, threshold: float = 0.6) -> bool:
    """True on the hidden-battle WARNING modal (a secret unit appears when a
    stage clears its hidden condition). Matches the top-center WARNING +
    不明機體出現 banner within HIDDEN_BATTLE_WARNING_REGION; measured 1.0 on
    the 20260705 popup frame and <=0.21 on hub / battle-map / phase-start
    frames, so the 0.6 gate sits in a wide empty gap well clear of
    TM_CCOEFF darkened-overlay matches."""
    template = cv2.imread(str(HIDDEN_BATTLE_WARNING_TEMPLATE))
    if template is None:
        return False
    x0, y0, w, h = HIDDEN_BATTLE_WARNING_REGION
    band = frame[y0 : y0 + h, x0 : x0 + w]
    if band.shape[0] < template.shape[0] or band.shape[1] < template.shape[1]:
        return False
    result = cv2.matchTemplate(band, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, _ = cv2.minMaxLoc(result)
    return score >= threshold


def is_unit_detail_modal(frame: np.ndarray, threshold: float = 0.6) -> bool:
    """True on the 單位設置詳情 unit-setup detail modal. A stray keyguard drag
    that lands on a map unit opens it over the live battle; the controller
    must detect it and tap 關閉 to escape instead of idling out. Matches the
    top-center title within UNIT_DETAIL_MODAL_REGION so a high TM_CCOEFF
    response cannot come from the dimmed map the modal draws behind itself."""
    template = _cached_template(str(UNIT_DETAIL_MODAL_TEMPLATE))
    if template is None:
        return False
    x0, y0, w, h = UNIT_DETAIL_MODAL_REGION
    band = frame[y0 : y0 + h, x0 : x0 + w]
    if band.shape[0] < template.shape[0] or band.shape[1] < template.shape[1]:
        return False
    result = cv2.matchTemplate(band, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, _ = cv2.minMaxLoc(result)
    return score >= threshold


def read_turn_number(frame: np.ndarray) -> int | None:
    """The on-screen TURN number, or None when the chip is absent or
    unreadable. Verified 4/4 on the calibrated captures and 19/19 on the
    HARD 1 run's archived half-scale JPEG frames (turn 1 -> 2 boundary
    the marker-diff compare missed live)."""
    return digits.read_number(
        frame,
        TURN_NUMBER_REGION,
        digit_height=TURN_DIGIT_HEIGHT,
        invert=True,
        allow_minus=False,
    )


def crop_turn_marker(frame: np.ndarray) -> np.ndarray:
    """Grayscale crop of the on-screen TURN number, for turn-change checks."""
    x0, y0, w, h = TURN_MARKER_REGION
    return cv2.cvtColor(frame[y0 : y0 + h, x0 : x0 + w], cv2.COLOR_BGR2GRAY)


def turn_marker_changed(
    prev: np.ndarray | None, cur: np.ndarray | None, threshold: float = 0.85
) -> bool:
    """True when the on-screen TURN number visibly differs between two hub
    frames. The same turn repaints the digit identically (self-correlation
    ~1.0); a new turn draws a different glyph and scores well under the gate.
    A missing prior marker counts as changed so the first turn is admitted."""
    if prev is None or cur is None or prev.shape != cur.shape:
        return True
    result = cv2.matchTemplate(cur, prev, cv2.TM_CCOEFF_NORMED)
    _, score, _, _ = cv2.minMaxLoc(result)
    return score < threshold


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


# --- game-forecast readers (reconciliation chain, M2) -----------------------
#
# Field regions below were calibrated on full-resolution PNG captures
# (20260712-182654 weapon select, 20260705-180119 battle prep 應戰,
# 20260711-214425 unit_move) by measuring white-text component boxes.
# The right-hand panel (our unit on weapon select, the defender on battle
# prep) lays out identically on both screens, so those regions are shared;
# the left panel does not (weapon select puts HP left of EN, battle prep
# the reverse).

_ELEMENTS = Path(__file__).resolve().parents[3] / "assets" / "templates" / "elements"

WEAPON_SELECT_HEADER_TEMPLATE = _ELEMENTS / "label_weapon_select.png"
BATTLE_PREP_HEADER_TEMPLATE = _ELEMENTS / "label_battle_prep.png"
PREP_REACTION_TEMPLATE = _ELEMENTS / "label_prep_reaction.png"
KILL_COUNTER_LABEL_TEMPLATE = _ELEMENTS / "label_kill_counter.png"

# both screen headers live top-left; highpass because a template captured
# over a dark map degrades on snowfields (0.674 raw vs 0.823 highpass for
# 選擇武裝, negatives stay <=0.46)
FORECAST_HEADER_REGION = (110, 0, 320, 135)
FORECAST_HEADER_THRESHOLD = 0.7
# the -應戰- suffix follows 戰鬥準備 in the header; its leading/trailing
# dashes keep it from matching the header's own 戰 (1.000 vs 0.253)
PREP_REACTION_REGION = (250, 0, 450, 100)
PREP_REACTION_THRESHOLD = 0.6

# the 破壞數 label floats right of the auto-sized TURN chip (measured x=296
# with "TURN 1", x=329 with "TURN 22"), so the counter digits are anchored
# to the matched label, not to fixed coordinates
KILL_LABEL_SEARCH_REGION = (250, 50, 350, 80)
KILL_LABEL_THRESHOLD = 0.75

WS_TARGET_HP_REGION = (660, 183, 130, 40)
WS_TARGET_EN_REGION = (855, 183, 80, 40)
WS_DAMAGE_REGION = (590, 228, 160, 44)
BP_ATTACKER_EN_REGION = (630, 184, 90, 36)
BP_ATTACKER_HP_REGION = (790, 180, 180, 40)
FORECAST_RIGHT_HP_REGION = (1500, 180, 145, 44)
FORECAST_RIGHT_EN_REGION = (1700, 180, 92, 44)
BP_ATTACK_REGION = (1090, 98, 190, 62)
BP_DEFENSE_REGION = (1090, 213, 190, 62)
BP_HP_DELTA_REGION = (1420, 238, 175, 36)

# bottom avatar row on 戰鬥準備: circles at y~938, centered on x~963 with a
# 200px pitch, so the row grows toward both edges with the participant count
# and every hit% must be found by scanning, not by fixed regions. each hit%
# is white text whose left edge sits on its avatar's center x; the ring arc
# right of the order badge (x0-56..x0-48, rows 846-860) carries the faction
# color (red enemy / blue ally, same vocabulary as the HP arcs). digits are
# a narrower typeface than the HUD numbers -- they read with the dedicated
# "hit" glyph set (assets/templates/digits/hit/, cropped off the 20260719
# PNG fixtures; '3' and '6' have no capture yet and will not read until one
# lands)
BP_HIT_ROW_REGION = (360, 833, 1200, 30)
BP_HIT_TOKEN_GAP = 40
BP_HIT_DIGIT_HEIGHT = 32
BP_HIT_FONT = "hit"
BP_HIT_RING_MIN_PIXELS = 25
AVATAR_ROW_CENTER_X = 963
AVATAR_ROW_Y = 938
AVATAR_SLOT_TOLERANCE = 18

# name bars end before each panel's bright edge line (x=938 left, x=1790
# right on the weapon-select capture) so the tight-bbox normalization in
# name_signature is driven by the glyphs, not by fixed panel furniture
FORECAST_LEFT_NAME_REGION = (555, 126, 375, 46)
FORECAST_RIGHT_NAME_REGION = (1420, 126, 365, 46)

# tap-enemy summary card (hub): name bar shares the forecast left band;
# digits measured on the single 20260705-153755 capture (dh30 confirmed by
# read confidence 0.87/0.92 -- component heights underestimate by 1-2px
# because anti-aliased stroke edges fall below the white threshold).
# threshold 0.88: battle-prep's attacker panel scores 0.798 on this anchor
# (EN label lookalike), everything else stays under 0.42
ENEMY_SUMMARY_ANCHOR_TEMPLATE = _ELEMENTS / "label_summary_hp.png"
ENEMY_SUMMARY_ANCHOR_REGION = (570, 175, 100, 65)
ENEMY_SUMMARY_ANCHOR_THRESHOLD = 0.88
ENEMY_SUMMARY_HP_REGION = (680, 182, 140, 44)
ENEMY_SUMMARY_EN_REGION = (865, 182, 100, 44)

# 支援防禦 pill on the defender (our, right) panel of -應戰- prep screens.
# 1.000 / 0.968 on the two 20260719 captures that carry it, <=0.58 on every
# other prep/menu fixture, so 0.8 splits with wide margin. only the reaction
# variant is calibrated: on -攻擊- the shielded unit would be the enemy on
# the left panel, whose label slot has no capture yet.
SUPPORT_DEFENSE_LABEL_TEMPLATE = _ELEMENTS / "label_support_defense.png"
SUPPORT_DEFENSE_SEARCH = (1380, 200, 300, 90)
SUPPORT_DEFENSE_THRESHOLD = 0.8

# 應戰 stance action row (opened by tapping our avatar on -應戰- prep): the
# row is a fixed-slot grid, right-anchored on the same pixels regardless of
# weapon count -- 閃避 at (1540,940), 防禦 one slot left at (1352,940),
# counter weapons continuing leftward at a 187px pitch (all four 20260719
# menu captures match the dodge icon at exactly (1540,940); the earlier
# "anchor shifts right with more weapons" note in docs/battle-prep-ui.md was
# a mis-scaled visual estimate). the 防禦 button repaints per mech: plain
# shield icon = defend (-20%), boxed shield-with-crest = shield (-40%, 防禦
# （盾牌）); the two crops anti-correlate (-0.12) so template argmax splits
# them. weapon slots are detected by their yellow "EN <cost>" caption
# (present even on disabled buttons) and classified enabled/disabled by icon
# brightness -- every user-confirmed disabled weapon idles at V~78 and every
# confirmed enabled one at V>=200, but the only SHORT captures all sit at
# V~76 with no confirmed-enabled sample, so a dark-but-enabled icon
# misreading as disabled is an open assumption to verify live (S10).
STANCE_DODGE_TEMPLATE = _ELEMENTS / "btn_stance_dodge.png"
STANCE_DEFEND_TEMPLATE = _ELEMENTS / "btn_stance_defend.png"
STANCE_SHIELD_TEMPLATE = _ELEMENTS / "btn_stance_shield.png"
STANCE_DODGE_SEARCH = (1450, 860, 180, 160)
STANCE_GUARD_SEARCH = (1262, 860, 180, 160)
STANCE_TEMPLATE_THRESHOLD = 0.8
STANCE_PITCH = 187
STANCE_ROW_Y = 940
STANCE_MIN_X = 340
STANCE_EN_CAPTION_BAND = (992, 24)
STANCE_EN_MIN_PIXELS = 60
STANCE_ICON_HALF = 14
STANCE_ENABLED_MIN_V = 120


@dataclass(frozen=True)
class WeaponSelectForecast:
    """The game's own prediction on the 選擇武裝 screen. None fields were
    not readable (panel occluded, animation frame) -- never guessed."""

    target_name_sig: str | None
    target_hp: int | None
    target_en: int | None
    predicted_damage: int | None
    hit_pct: int | None
    our_name_sig: str | None
    our_hp: int | None
    our_en: int | None


@dataclass(frozen=True)
class EnemySummary:
    """The tap-enemy summary card on the hub (scouting)."""

    name_sig: str | None
    hp: int | None
    en: int | None


@dataclass(frozen=True)
class AvatarHit:
    """One hit% readout scanned off the bottom avatar row. x is the pct
    text's left edge == that avatar's circle center; faction comes from the
    ring-arc color (None when the arc sample is too weak to call)."""

    x: int
    pct: int
    faction: str | None


@dataclass(frozen=True)
class StanceOption:
    """One tappable option on the 應戰 stance action row. stance uses the
    sim DefenseKind vocabulary; weapon_index counts counter weapons from
    the 防禦 button leftward (0 = the slot next to it)."""

    stance: str
    tap: tuple[int, int]
    enabled: bool
    weapon_index: int | None = None


@dataclass(frozen=True)
class ReactionStanceMenu:
    """The 應戰 stance action row read off a -應戰- prep frame after our
    avatar was tapped. guard is the 防禦 slot -- defend or shield depending
    on the mech (None when neither icon template clears the gate, e.g. an
    unseen selected-state repaint)."""

    dodge: StanceOption
    guard: StanceOption | None
    counters: tuple[StanceOption, ...]

    @property
    def available_stances(self) -> tuple[str, ...]:
        stances = [self.dodge.stance]
        if self.guard is not None:
            stances.append(self.guard.stance)
        if any(c.enabled for c in self.counters):
            stances.append(DefenseKind.COUNTER)
        return tuple(stances)


@dataclass(frozen=True)
class BattlePrepForecast:
    """The game's prediction on the 戰鬥準備 confirmation. Panel factions
    are fixed on both variants (calibrated 2026-07-19): the left panel is
    always the enemy, the right always ours. The attacker_*/defender_*
    field names describe the -應戰- case (enemy initiates from the left);
    on our own -攻擊- read them as left/right -- the "attacker" panel is
    then our target, and is_reaction carries the direction.

    The reaction (#3, 應戰決策) is this same screen in its -應戰- variant,
    not a separate popup. hit_pct is the initiator's hit chance scanned off
    the bottom avatar row (the enemy attack on -應戰-, our attack
    otherwise). support_defense is the 支援防禦 pill read on -應戰- (bool);
    on -攻擊- it stays None because the enemy-side label slot is
    uncalibrated. available_stances stays None here: the offered set lives
    on the stance action row, which only exists after the controller taps
    our avatar and reads that frame with read_reaction_stance_menu (S9d
    wiring pending) -- this reader never guesses it from the main screen."""

    is_reaction: bool
    attack_value: int | None
    defense_value: int | None
    hit_pct: int | None
    attacker_name_sig: str | None
    attacker_hp: int | None
    attacker_en: int | None
    defender_name_sig: str | None
    defender_hp: int | None
    defender_en: int | None
    defender_hp_delta: int | None
    support_defense: bool | None
    available_stances: tuple[str, ...] | None = None


def _anchor_score(
    frame: np.ndarray, template_path: Path, region: tuple[int, int, int, int]
) -> float:
    template = _cached_template(str(template_path))
    if template is None:
        return 0.0
    crop = _crop(frame, region)
    if crop.shape[0] < template.shape[0] or crop.shape[1] < template.shape[1]:
        return 0.0
    result = cv2.matchTemplate(_highpass(crop), _highpass(template), cv2.TM_CCOEFF_NORMED)
    return float(result.max())


def name_signature(
    frame: np.ndarray, region: tuple[int, int, int, int], threshold: int = 160
) -> str | None:
    """64-bit dHash of the white name text inside `region`, or None when no
    text is present. The glyph mask is tight-bbox-normalized first because
    the name's start position floats a few tens of pixels between screens
    (icon width, panel variant); the hash must identify the unit, not the
    layout. Icons inside the band are hashed along with the text: if a
    status icon changes, the signature changes and downstream caches
    re-read -- noisy but safe. Components under 8px tall are ignored so a
    panel border line drifting into the band cannot stretch the bbox."""
    band = cv2.cvtColor(_crop(frame, region), cv2.COLOR_BGR2GRAY)
    if band.size == 0:
        return None
    mask = (band >= threshold).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    keep = [i for i in range(1, n) if stats[i][4] >= 15 and stats[i][3] >= 8]
    if not keep:
        return None
    x0 = min(stats[i][0] for i in keep)
    y0 = min(stats[i][1] for i in keep)
    x1 = max(stats[i][0] + stats[i][2] for i in keep)
    y1 = max(stats[i][1] + stats[i][3] for i in keep)
    tight = band[y0:y1, x0:x1]
    small = cv2.resize(tight, (9, 8), interpolation=cv2.INTER_AREA)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    return f"{int(''.join('1' if b else '0' for b in bits), 2):016x}"


def read_kill_counter(frame: np.ndarray) -> tuple[int, int] | None:
    """The 破壞數 k/m counter shown on hub / unit-move / weapon-select /
    battle-prep headers. None when the label anchor is absent or the digits
    do not read as a clean fraction -- the header strip is translucent, and
    white digits over a bright busy map (snowfield with a sprite behind)
    can fall below the match gate; callers retry on a later frame."""
    template = _cached_template(str(KILL_COUNTER_LABEL_TEMPLATE))
    if template is None:
        return None
    gray = cv2.cvtColor(_crop(frame, KILL_LABEL_SEARCH_REGION), cv2.COLOR_BGR2GRAY)
    tgray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    result = cv2.matchTemplate(gray, tgray, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(result)
    if score < KILL_LABEL_THRESHOLD:
        return None
    x0, y0, _, _ = KILL_LABEL_SEARCH_REGION
    band = (
        x0 + loc[0] + tgray.shape[1] - 4,
        y0 + loc[1] - 10,
        140,
        44,
    )
    return digits.read_fraction(frame, band, digit_height=23)


def is_battle_prep_reaction(frame: np.ndarray) -> bool:
    """True when the battle-prep header carries the -應戰- suffix (the enemy
    initiated; left panel is theirs)."""
    template = _cached_template(str(PREP_REACTION_TEMPLATE))
    if template is None:
        return False
    gray = cv2.cvtColor(_crop(frame, PREP_REACTION_REGION), cv2.COLOR_BGR2GRAY)
    tgray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    result = cv2.matchTemplate(gray, tgray, cv2.TM_CCOEFF_NORMED)
    _, score, _, _ = cv2.minMaxLoc(result)
    return score >= PREP_REACTION_THRESHOLD


def _magnitude(value: int | None) -> int | None:
    return None if value is None else abs(value)


def _match_color(
    frame: np.ndarray, template_path: Path, region: tuple[int, int, int, int]
) -> tuple[float, tuple[int, int]]:
    """Best raw-BGR TM_CCOEFF_NORMED score inside `region` and the matched
    center. Raw color (no highpass) because these templates carry their own
    icon artwork against a dark disc, where the color contrast is the
    signal."""
    template = _cached_template(str(template_path))
    if template is None:
        return 0.0, (0, 0)
    x, y, w, h = region
    crop = frame[y : y + h, x : x + w]
    if crop.shape[0] < template.shape[0] or crop.shape[1] < template.shape[1]:
        return 0.0, (0, 0)
    result = cv2.matchTemplate(crop, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(result)
    center = (
        x + loc[0] + template.shape[1] // 2,
        y + loc[1] + template.shape[0] // 2,
    )
    return float(score), center


def _ring_faction(hsv: np.ndarray, x: int) -> str | None:
    """Faction of the avatar whose hit% text starts at column x, from the
    ring-arc pixels between the order badge and the text (rows 846-860).
    Same color vocabulary as the map HP arcs: red enemy, blue ally."""
    window = hsv[846:860, max(0, x - 56) : max(0, x - 48)]
    if window.size == 0:
        return None
    strong = window[(window[..., 1] > 120) & (window[..., 2] > 90)]
    if strong.shape[0] < BP_HIT_RING_MIN_PIXELS:
        return None
    hues = strong[:, 0].astype(int)
    red = int(((hues >= 168) | (hues <= 12)).sum())
    blue = int(((hues >= 95) & (hues <= 135)).sum())
    if red > blue:
        return "enemy"
    if blue > red:
        return "ally"
    return None


def read_avatar_hits(frame: np.ndarray) -> tuple[AvatarHit, ...]:
    """Every hit% on the bottom avatar row, left to right. Scanning, not
    fixed regions: the row is centered and grows with the participant
    count. Tokens are the white pct glyphs (full-height components in the
    row band, clustered on x-gaps); each is OCRed with the hit glyph set
    and tagged with its avatar's ring color."""
    x0, y0, w, h = BP_HIT_ROW_REGION
    band = cv2.cvtColor(_crop(frame, BP_HIT_ROW_REGION), cv2.COLOR_BGR2GRAY)
    mask = (band >= 190).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    xs = sorted(
        int(stats[i][0])
        for i in range(1, n)
        if stats[i][4] >= 40 and stats[i][3] >= 24
    )
    if not xs:
        return ()
    starts = [xs[0]]
    last = xs[0]
    for x in xs[1:]:
        if x - last > BP_HIT_TOKEN_GAP:
            starts.append(x)
        last = x
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hits = []
    for start in starts:
        text_x = x0 + start
        pct = digits.read_percent(
            frame,
            (text_x - 8, 828, 100, 40),
            digit_height=BP_HIT_DIGIT_HEIGHT,
            font=BP_HIT_FONT,
        )
        if pct is None:
            continue
        hits.append(AvatarHit(x=text_x, pct=pct, faction=_ring_faction(hsv, text_x)))
    return tuple(hits)


def defender_avatar_slot(
    hits: tuple[AvatarHit, ...], support_defense: bool
) -> tuple[int, int] | None:
    """Slot center of the defending (rightmost) avatar on a -應戰- prep
    frame -- the stance-menu entry point -- derived arithmetically, not by
    pixel probing: the avatar circles are portrait art over arbitrary map
    background (a blue-water map defeats every ring-color heuristic tried),
    while the row geometry is exact. The row is centered on x=963 with a
    200px pitch, so every slot lands on the 100px half-grid; the avatar
    count is (pct-bearing avatars) + (the label-flagged interceptor) + the
    defender itself when its current stance shows no pct (dodge/defend) --
    and the row-centering parity constraint (N-1 ≡ (token_x-963)/100 mod 2)
    picks exactly one of those two hypotheses. Validated 5/5 on the
    20260719 reaction fixtures. None on no hits, an off-grid token, or
    inconsistent parity (layout surprise -- the caller aborts rather than
    guessing); the caller must still verify the tap actually opened the
    stance row (read_reaction_stance_menu), which catches a wrong count."""
    if not hits:
        return None
    offsets = []
    for h in hits:
        off = h.x - AVATAR_ROW_CENTER_X
        residue = off % 100
        if min(residue, 100 - residue) > AVATAR_SLOT_TOLERANCE:
            return None
        offsets.append(round(off / 100))
    if len({d % 2 for d in offsets}) != 1:
        return None
    parity = offsets[0] % 2
    base = len(hits) + (1 if support_defense else 0)
    count = base if (base - 1) % 2 == parity else base + 1
    if count < 2:
        count += 2
    x = AVATAR_ROW_CENTER_X + (count - 1) * 100
    if max(h.x for h in hits) > x + AVATAR_SLOT_TOLERANCE:
        return None
    return (x, AVATAR_ROW_Y)


def _initiator_hit(hits: tuple[AvatarHit, ...], is_reaction: bool) -> int | None:
    """The initiating attack's hit% -- the enemy's (red ring) on -應戰-,
    ours on -攻擊-. Our main attack is the rightmost blue with a pct:
    supports sit left of it and the enemy counter right of it, and
    non-participants carry no pct."""
    if is_reaction:
        return next((h.pct for h in hits if h.faction == "enemy"), None)
    ally = [h for h in hits if h.faction == "ally"]
    return ally[-1].pct if ally else None


def has_support_defense_label(frame: np.ndarray) -> bool:
    """True when the 支援防禦 pill sits on the defender (right) panel -- an
    ally interceptor will absorb the incoming hit. Calibrated for -應戰-
    only (see SUPPORT_DEFENSE_LABEL_TEMPLATE)."""
    score, _ = _match_color(
        frame, SUPPORT_DEFENSE_LABEL_TEMPLATE, SUPPORT_DEFENSE_SEARCH
    )
    return score >= SUPPORT_DEFENSE_THRESHOLD


def read_reaction_stance_menu(frame: np.ndarray) -> ReactionStanceMenu | None:
    """The 應戰 stance action row, or None when its dodge anchor is not on
    screen (main prep screen, -攻擊- support weapon menu whose right anchor
    is 不參加, skill menu, ...). Weapon slots run leftward from 防禦 on the
    fixed 187px pitch until a slot has no yellow EN caption; enabled comes
    from icon brightness (see the constants block for the open SHORT
    assumption)."""
    dodge_score, dodge_center = _match_color(
        frame, STANCE_DODGE_TEMPLATE, STANCE_DODGE_SEARCH
    )
    if dodge_score < STANCE_TEMPLATE_THRESHOLD:
        return None
    defend_score, defend_center = _match_color(
        frame, STANCE_DEFEND_TEMPLATE, STANCE_GUARD_SEARCH
    )
    shield_score, shield_center = _match_color(
        frame, STANCE_SHIELD_TEMPLATE, STANCE_GUARD_SEARCH
    )
    guard: StanceOption | None = None
    guard_x = dodge_center[0] - (STANCE_PITCH + 1)
    if max(defend_score, shield_score) >= STANCE_TEMPLATE_THRESHOLD:
        if defend_score >= shield_score:
            kind, center = DefenseKind.DEFEND, defend_center
        else:
            kind, center = DefenseKind.SHIELD, shield_center
        guard = StanceOption(stance=kind, tap=center, enabled=True)
        guard_x = center[0]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    caption_y, caption_h = STANCE_EN_CAPTION_BAND
    counters = []
    for k in range(1, 8):
        x = guard_x - STANCE_PITCH * k
        if x < STANCE_MIN_X:
            break
        caption = hsv[caption_y : caption_y + caption_h, x - 70 : x + 70]
        yellow = (
            (caption[..., 0] >= 18)
            & (caption[..., 0] <= 40)
            & (caption[..., 1] >= 140)
            & (caption[..., 2] >= 150)
        )
        if int(yellow.sum()) < STANCE_EN_MIN_PIXELS:
            break
        icon = hsv[
            STANCE_ROW_Y - STANCE_ICON_HALF : STANCE_ROW_Y + STANCE_ICON_HALF,
            x - STANCE_ICON_HALF : x + STANCE_ICON_HALF,
            2,
        ]
        counters.append(
            StanceOption(
                stance=DefenseKind.COUNTER,
                tap=(x, STANCE_ROW_Y),
                enabled=float(icon.mean()) >= STANCE_ENABLED_MIN_V,
                weapon_index=k - 1,
            )
        )
    return ReactionStanceMenu(
        dodge=StanceOption(stance=DefenseKind.DODGE, tap=dodge_center, enabled=True),
        guard=guard,
        counters=tuple(counters),
    )


def read_enemy_summary(frame: np.ndarray) -> EnemySummary | None:
    """The summary card that pops after tapping an enemy on the hub, or
    None when its HP-label anchor is not on screen. Callers should only
    consult this in hub context: the battle-prep attacker panel scores
    within 0.09 of the anchor gate."""
    template = _cached_template(str(ENEMY_SUMMARY_ANCHOR_TEMPLATE))
    if template is None:
        return None
    gray = cv2.cvtColor(_crop(frame, ENEMY_SUMMARY_ANCHOR_REGION), cv2.COLOR_BGR2GRAY)
    tgray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    result = cv2.matchTemplate(gray, tgray, cv2.TM_CCOEFF_NORMED)
    _, score, _, _ = cv2.minMaxLoc(result)
    if score < ENEMY_SUMMARY_ANCHOR_THRESHOLD:
        return None
    return EnemySummary(
        name_sig=name_signature(frame, FORECAST_LEFT_NAME_REGION),
        hp=digits.read_number(
            frame, ENEMY_SUMMARY_HP_REGION, digit_height=30, allow_minus=False
        ),
        en=digits.read_number(
            frame, ENEMY_SUMMARY_EN_REGION, digit_height=30, allow_minus=False
        ),
    )


def read_weapon_select_forecast(frame: np.ndarray) -> WeaponSelectForecast | None:
    """Game forecast off the 選擇武裝 screen, or None when its header is not
    on screen. hit_pct is a v1 stub (always None): the 🎯NN% readout floats
    over the targeted unit on the map instead of sitting at a fixed region,
    and the only capture on hand has it clipped by the screen edge --
    battle-prep carries the authoritative hit number for reconciliation."""
    if _anchor_score(frame, WEAPON_SELECT_HEADER_TEMPLATE, FORECAST_HEADER_REGION) < (
        FORECAST_HEADER_THRESHOLD
    ):
        return None
    return WeaponSelectForecast(
        target_name_sig=name_signature(frame, FORECAST_LEFT_NAME_REGION),
        target_hp=digits.read_number(
            frame, WS_TARGET_HP_REGION, digit_height=30, allow_minus=False
        ),
        target_en=digits.read_number(
            frame, WS_TARGET_EN_REGION, digit_height=30, allow_minus=False
        ),
        predicted_damage=_magnitude(
            digits.read_number(frame, WS_DAMAGE_REGION, digit_height=32)
        ),
        hit_pct=None,
        our_name_sig=name_signature(frame, FORECAST_RIGHT_NAME_REGION),
        our_hp=digits.read_number(
            frame, FORECAST_RIGHT_HP_REGION, digit_height=32, allow_minus=False
        ),
        our_en=digits.read_number(
            frame, FORECAST_RIGHT_EN_REGION, digit_height=30, allow_minus=False
        ),
    )


def read_battle_prep_forecast(frame: np.ndarray) -> BattlePrepForecast | None:
    """Game forecast off the 戰鬥準備 confirmation, or None when its header
    is not on screen. hit_pct comes from the avatar-row scan (initiator's
    hit chance); support_defense from the 支援防禦 pill on -應戰- and stays
    None on -攻擊- (enemy-side label uncalibrated). available_stances is
    never filled here -- see BattlePrepForecast and
    read_reaction_stance_menu."""
    if _anchor_score(frame, BATTLE_PREP_HEADER_TEMPLATE, FORECAST_HEADER_REGION) < (
        FORECAST_HEADER_THRESHOLD
    ):
        return None
    is_reaction = is_battle_prep_reaction(frame)
    return BattlePrepForecast(
        is_reaction=is_reaction,
        attack_value=digits.read_number(
            frame, BP_ATTACK_REGION, digit_height=48, allow_minus=False, font="attack"
        ),
        defense_value=digits.read_number(
            frame, BP_DEFENSE_REGION, digit_height=48, allow_minus=False, font="attack"
        ),
        hit_pct=_initiator_hit(read_avatar_hits(frame), is_reaction),
        attacker_name_sig=name_signature(frame, FORECAST_LEFT_NAME_REGION),
        attacker_hp=digits.read_number(
            frame, BP_ATTACKER_HP_REGION, digit_height=32, allow_minus=False
        ),
        attacker_en=digits.read_number(
            frame, BP_ATTACKER_EN_REGION, digit_height=30, allow_minus=False
        ),
        defender_name_sig=name_signature(frame, FORECAST_RIGHT_NAME_REGION),
        defender_hp=digits.read_number(
            frame, FORECAST_RIGHT_HP_REGION, digit_height=32, allow_minus=False
        ),
        defender_en=digits.read_number(
            frame, FORECAST_RIGHT_EN_REGION, digit_height=30, allow_minus=False
        ),
        defender_hp_delta=_magnitude(
            digits.read_number(frame, BP_HP_DELTA_REGION, digit_height=30)
        ),
        support_defense=has_support_defense_label(frame) if is_reaction else None,
        available_stances=None,
    )
