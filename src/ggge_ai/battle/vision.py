"""Pixel-level helpers for the manual battle controller.

All coordinates are in the 2340x1080 landscape reference frame.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

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
BP_HIT_REGION = (846, 812, 90, 44)

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
class BattlePrepForecast:
    """The game's prediction on the 戰鬥準備 confirmation. Attacker is
    always the left panel: our unit on our attacks, the enemy on -應戰-
    reactions -- is_reaction carries the direction."""

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


def signature_distance(a: str | None, b: str | None) -> int:
    """Hamming distance between two name signatures; unknowns are maximally
    distant so a None never aliases a real unit."""
    if a is None or b is None:
        return 64
    return (int(a, 16) ^ int(b, 16)).bit_count()


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
    is not on screen. support_defense is a v1 stub (always None = unknown,
    never False): no capture of the support-defense icon exists yet to crop
    a template from."""
    if _anchor_score(frame, BATTLE_PREP_HEADER_TEMPLATE, FORECAST_HEADER_REGION) < (
        FORECAST_HEADER_THRESHOLD
    ):
        return None
    return BattlePrepForecast(
        is_reaction=is_battle_prep_reaction(frame),
        attack_value=digits.read_number(
            frame, BP_ATTACK_REGION, digit_height=48, allow_minus=False
        ),
        defense_value=digits.read_number(
            frame, BP_DEFENSE_REGION, digit_height=48, allow_minus=False
        ),
        hit_pct=digits.read_percent(frame, BP_HIT_REGION, digit_height=23),
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
        support_defense=None,
    )
