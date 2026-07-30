"""單位詳情 / 單位設置詳情 panel parsing: layout anchors and numeric fields.

Two panel families share most of the layout. 單位設置詳情 opens inside a stage
(enemy Inspect and our own units) and carries a pilot block; 單位詳情 opens off
the 強化 hub and carries the mech alone. Both offer a 詳情/基本資訊 pair of views
and, in the 詳情 view, three tabs; the weapon table is pixel-identical between
them, so one reader covers both.

Nothing here is at a fixed pitch that the game does not actually hold fixed:

- weapon cards are located by their LV/RANGE header strip colour, because a
  card grows by one row when the weapon has an effect note, so a fixed pitch
  drifts off after the first noted weapon;
- the header strip's own cells are re-measured per card, because ammunition
  weapons add a 7th 彈藥量 column and re-flow every other column;
- 基本資訊 rows hang off the HP/EN/SP bars, because our units show an LV row
  that enemy units do not.

The stat column is a trap worth naming: on the 能力、OP tab the panel replaces
absolute stats with the ability-granted delta ('+N', blue). StatColumn keeps
each slot's StatReading so callers see delta=True instead of a wrong absolute,
and StatColumn.absolute hands back only values that are really stats.
Free text (weapon names, notes, ability wording) is not read here: this module
returns the crop regions and runtime.panel_text owns that channel.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import cv2
import numpy as np

from . import glyphs
from .glyphs import Ink, Region, StatReading

TEMPLATE_ROOT = Path(__file__).resolve().parents[3] / "assets" / "templates" / "panels"

TITLE_REGION = (1040, 76, 290, 42)
TITLE_THRESHOLD = 0.70
TAB_BANDS = ((940, 166, 90, 14), (1370, 166, 90, 14), (1790, 166, 90, 14))
TAB_ACTIVE_MARGIN = 60

CONTENT_REGION = (790, 226, 1230, 684)

SIDEBAR_VALUE_X = 596
SIDEBAR_VALUE_W = 148
SIDEBAR_VALUE_H = 32
STAGE_UNIT_ROWS = (254, 302, 350, 398, 446, 494)
STAGE_PILOT_ROWS = (600, 648, 696, 744, 792, 840)
ROSTER_UNIT_ROWS = (242, 290, 338, 386, 434, 482)

HEADER_STRIP_BGR = (188, 156, 143)
HEADER_PROBE_X = (970, 1070)
HEADER_STRIP_TOLERANCE = 30
HEADER_STRIP_MIN_H = 30
HEADER_CELL_TOLERANCE = 45
HEADER_CELL_MIN_W = 50
HEADER_CELL_GAP = 2
HEADER_STRIP_GAP = 3
HEADER_CELL_LEFT = 900
CELL_INSET = 4
VALUE_OFFSET_Y = 37
VALUE_H = 38
NAME_OFFSET_Y = -64
NAME_REGION_X = (940, 850)
NAME_H = 52
BADGE_OFFSET_Y = -61
BADGE_REGION_X = (1470, 530)
BADGE_H = 43
BADGE_THRESHOLD = 0.72
NOTE_OFFSET_Y = 92
NOTE_H = 66
GAP_PROBE_X = (1700, 250)
GAP_PROBE_Y = (76, 200)
GAP_DARK = 185
GAP_SHORT_LIMIT = 120

BAR_X = (1170, 150)
BAR_SEARCH_Y = (120, 500)
SP_BAR_X = (1930, 130)
HP_HUE = (100, 125)
EN_HUE = (10, 28)
SP_HUE = (45, 90)
BAR_MIN_PIXELS = 60
VITAL_VALUE_X = (1150, 180)
VITAL_OFFSET_Y = -39
VITAL_H = 34
LV_OFFSET_Y = -95
MOVE_OFFSET_Y = 22
MOVE_VALUE_X = (1250, 90)
FACTION_OFFSET_Y = 68
FACTION_REGION = (1140, 0, 130, 30)
PILOT_VALUE_X = (1975, 95)
MP_REGION = (1780, 608, 95, 44)
CS_BADGE_REGION = (1810, 176, 260, 34)
CS_BADGE_THRESHOLD = 0.72
CS_BADGE_MIN_GAP = 20

MELEE = "melee"
SHOOTING = "shooting"
AWAKENING = "awakening"
CATEGORY_TEMPLATES = {
    MELEE: "badge_melee.png",
    SHOOTING: "badge_shooting.png",
    AWAKENING: "badge_awakening.png",
}

ENEMY = "enemy"
ALLY = "ally"


class PanelKind(StrEnum):
    STAGE_BASIC = "stage_basic"
    STAGE_COMBO = "stage_combo"
    STAGE_WEAPONS = "stage_weapons"
    STAGE_ABILITIES = "stage_abilities"
    ROSTER_UNIT_BASIC = "roster_unit_basic"
    ROSTER_UNIT_INFO = "roster_unit_info"
    ROSTER_UNIT_WEAPONS = "roster_unit_weapons"
    ROSTER_UNIT_ABILITIES = "roster_unit_abilities"
    ROSTER_PILOT = "roster_pilot"
    UNKNOWN = "unknown"


STAGE_KINDS = (
    PanelKind.STAGE_BASIC,
    PanelKind.STAGE_COMBO,
    PanelKind.STAGE_WEAPONS,
    PanelKind.STAGE_ABILITIES,
)
WEAPON_KINDS = (PanelKind.STAGE_WEAPONS, PanelKind.ROSTER_UNIT_WEAPONS)
ABILITY_KINDS = (PanelKind.STAGE_ABILITIES, PanelKind.ROSTER_UNIT_ABILITIES)
BASIC_KINDS = (PanelKind.STAGE_BASIC, PanelKind.ROSTER_UNIT_BASIC)


@dataclass(frozen=True)
class StatColumn:
    """The left stat rail. Every slot is a StatReading, delta flag included."""

    kind: PanelKind
    max_hp: StatReading
    en_max: StatReading
    move_range: StatReading
    unit_attack: StatReading
    unit_defense: StatReading
    mobility: StatReading
    pilot_shooting: StatReading = StatReading(None)
    pilot_melee: StatReading = StatReading(None)
    pilot_awakening: StatReading = StatReading(None)
    pilot_defense: StatReading = StatReading(None)
    pilot_reaction: StatReading = StatReading(None)
    pilot_sp: StatReading = StatReading(None)

    @property
    def deltas(self) -> tuple[str, ...]:
        return tuple(name for name, slot in self.slots() if slot.delta)

    @property
    def unread(self) -> tuple[str, ...]:
        return tuple(name for name, slot in self.slots() if slot.value is None)

    def absolute(self, name: str) -> int | None:
        return getattr(self, name).absolute

    def slots(self) -> tuple[tuple[str, StatReading], ...]:
        names = (
            "max_hp",
            "en_max",
            "move_range",
            "unit_attack",
            "unit_defense",
            "mobility",
            "pilot_shooting",
            "pilot_melee",
            "pilot_awakening",
            "pilot_defense",
            "pilot_reaction",
            "pilot_sp",
        )
        return tuple((name, getattr(self, name)) for name in names)


@dataclass(frozen=True)
class WeaponRowRead:
    """One weapon card's numeric row plus the crops its free text lives in."""

    index: int
    categories: tuple[str, ...]
    level: int | None
    range_min: int | None
    range_max: int | None
    map_weapon: bool
    power: int | None
    en_cost: int | None
    hit_pct: int | None
    crit_pct: int | None
    ammo: int | None
    has_ammo_column: bool
    name_region: Region
    note_region: Region | None
    clipped: bool


@dataclass(frozen=True)
class BasicView:
    """The 基本資訊 side-by-side overview."""

    max_hp: int | None
    en_max: int | None
    move_range: int | None
    unit_lv: int | None
    faction: str | None
    pilot_lv: int | None
    pilot_sp: int | None
    mp_current: int | None
    mp_max: int | None
    chance_step_badges: int | None


@functools.cache
def _template(name: str) -> np.ndarray | None:
    return cv2.imread(str(TEMPLATE_ROOT / name), cv2.IMREAD_GRAYSCALE)


def _match(frame: np.ndarray, name: str, region: Region) -> float:
    template = _template(name)
    if template is None:
        return 0.0
    patch = glyphs.crop(frame, region)
    if patch.size == 0:
        return 0.0
    gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    if gray.shape[0] < template.shape[0] or gray.shape[1] < template.shape[1]:
        return 0.0
    return float(cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED).max())


def _match_positions(
    frame: np.ndarray, name: str, region: Region, threshold: float, min_gap: int
) -> tuple[int, ...]:
    template = _template(name)
    if template is None:
        return ()
    patch = glyphs.crop(frame, region)
    if patch.size == 0:
        return ()
    gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    if gray.shape[0] < template.shape[0] or gray.shape[1] < template.shape[1]:
        return ()
    result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
    hits = sorted(
        ((float(result[y, x]), int(x)) for y, x in zip(*np.where(result >= threshold))),
        reverse=True,
    )
    kept: list[int] = []
    for _, x in hits:
        if all(abs(x - other) >= min_gap for other in kept):
            kept.append(x)
    return tuple(sorted(region[0] + x for x in kept))


def _active_tab(frame: np.ndarray) -> int | None:
    for index, band in enumerate(TAB_BANDS):
        patch = glyphs.crop(frame, band)
        if patch.size == 0:
            continue
        blue, _, red = patch.reshape(-1, 3).mean(0)
        if blue - red >= TAB_ACTIVE_MARGIN:
            return index
    return None


def classify(frame: np.ndarray) -> PanelKind:
    """Which panel and tab is on screen, or UNKNOWN.

    The title separates the families and the pilot page; the active tab's blue
    fill separates the tabs. No active tab means the 基本資訊 view, whose
    content occupies the tab strip's rows."""
    scores = {
        PanelKind.STAGE_BASIC: _match(frame, "title_stage_unit.png", TITLE_REGION),
        PanelKind.ROSTER_UNIT_BASIC: _match(frame, "title_roster_unit.png", TITLE_REGION),
        PanelKind.ROSTER_PILOT: _match(frame, "title_roster_pilot.png", TITLE_REGION),
    }
    family, score = max(scores.items(), key=lambda item: item[1])
    if score < TITLE_THRESHOLD:
        return PanelKind.UNKNOWN
    if family is PanelKind.ROSTER_PILOT:
        return PanelKind.ROSTER_PILOT
    tab = _active_tab(frame)
    if tab is None:
        return family
    if family is PanelKind.STAGE_BASIC:
        return (PanelKind.STAGE_COMBO, PanelKind.STAGE_WEAPONS, PanelKind.STAGE_ABILITIES)[tab]
    return (
        PanelKind.ROSTER_UNIT_INFO,
        PanelKind.ROSTER_UNIT_WEAPONS,
        PanelKind.ROSTER_UNIT_ABILITIES,
    )[tab]


def _stat(frame: np.ndarray, row_y: int) -> StatReading:
    return glyphs.read_stat(
        frame, (SIDEBAR_VALUE_X, row_y, SIDEBAR_VALUE_W, SIDEBAR_VALUE_H)
    )


def read_stat_column(frame: np.ndarray, kind: PanelKind | None = None) -> StatColumn | None:
    """The left stat rail of any 詳情-view tab, or None on a panel without one."""
    kind = classify(frame) if kind is None else kind
    if kind in BASIC_KINDS or kind in (PanelKind.UNKNOWN, PanelKind.ROSTER_PILOT):
        return None
    stage = kind in STAGE_KINDS
    unit = [_stat(frame, y) for y in (STAGE_UNIT_ROWS if stage else ROSTER_UNIT_ROWS)]
    pilot = [_stat(frame, y) for y in STAGE_PILOT_ROWS] if stage else [StatReading(None)] * 6
    return StatColumn(
        kind=kind,
        max_hp=unit[0],
        en_max=unit[1],
        move_range=unit[2],
        unit_attack=unit[3],
        unit_defense=unit[4],
        mobility=unit[5],
        pilot_shooting=pilot[0],
        pilot_melee=pilot[1],
        pilot_awakening=pilot[2],
        pilot_defense=pilot[3],
        pilot_reaction=pilot[4],
        pilot_sp=pilot[5],
    )


def _colour_runs(
    values: np.ndarray, offset: int, minimum: int
) -> tuple[tuple[int, int], ...]:
    ys = np.where(values >= minimum)[0]
    if len(ys) == 0:
        return ()
    runs: list[tuple[int, int]] = []
    start = int(ys[0])
    for previous, current in zip(ys, ys[1:]):
        if current - previous > 1:
            runs.append((start + offset, int(previous) + offset))
            start = int(current)
    runs.append((start + offset, int(ys[-1]) + offset))
    return tuple(runs)


def _merge_runs(runs: tuple[tuple[int, int], ...], gap: int) -> tuple[tuple[int, int], ...]:
    merged: list[list[int]] = []
    for left, right in runs:
        if merged and left - merged[-1][1] - 1 <= gap:
            merged[-1][1] = right
        else:
            merged.append([left, right])
    return tuple((a, b) for a, b in merged)


def header_strips(frame: np.ndarray) -> tuple[tuple[int, int], ...]:
    """Every visible weapon card's LV/RANGE header strip, top to bottom.

    The strip's own label row breaks the colour run, so runs are stitched
    across small gaps before the height filter."""
    x0, x1 = HEADER_PROBE_X
    column = frame[:, x0:x1].astype(np.int32).mean(1)
    distance = np.abs(column - np.array(HEADER_STRIP_BGR)).sum(1)
    runs = _colour_runs((distance < HEADER_STRIP_TOLERANCE).astype(np.int32), 0, 1)
    stitched = _merge_runs(runs, HEADER_STRIP_GAP)
    return tuple(run for run in stitched if run[1] - run[0] >= HEADER_STRIP_MIN_H)


def header_cells(frame: np.ndarray, strip_top: int) -> tuple[tuple[int, int], ...]:
    """The strip's column cells: six normally, seven when the weapon has ammo."""
    row = frame[strip_top + 2].astype(np.int32)
    distance = np.abs(row - np.array(HEADER_STRIP_BGR)).sum(1)
    mask = (distance < HEADER_CELL_TOLERANCE).astype(np.int32)
    mask[:HEADER_CELL_LEFT] = 0
    runs = _merge_runs(_colour_runs(mask, 0, 1), HEADER_CELL_GAP)
    return tuple((a, b) for a, b in runs if b - a >= HEADER_CELL_MIN_W)


def _categories(frame: np.ndarray, strip_top: int) -> tuple[str, ...]:
    x, w = BADGE_REGION_X
    region = (x, strip_top + BADGE_OFFSET_Y, w, BADGE_H)
    found: list[tuple[int, str]] = []
    for name, template in CATEGORY_TEMPLATES.items():
        for position in _match_positions(frame, template, region, BADGE_THRESHOLD, 80):
            found.append((position, name))
    return tuple(name for _, name in sorted(found))


def _note_region(frame: np.ndarray, strip_top: int) -> Region | None:
    """The effect line under a card, or None when the card has none.

    A card with a note is one row taller, so the seam to the next card moves
    from strip+90 to strip+158. The seam is probed on the card's right margin,
    which note text never reaches -- probing where the note itself sits cannot
    tell a short note from no note.
    """
    y0, y1 = GAP_PROBE_Y
    band = frame[strip_top + y0 : strip_top + y1, GAP_PROBE_X[0] : sum(GAP_PROBE_X), 2]
    if band.size == 0:
        return None
    dark = np.where(band.astype(np.float64).mean(1) < GAP_DARK)[0]
    if len(dark) and int(dark[0]) + y0 <= GAP_SHORT_LIMIT:
        return None
    return (NAME_REGION_X[0], strip_top + NOTE_OFFSET_Y, NAME_REGION_X[1], NOTE_H)


def read_weapon_rows(frame: np.ndarray, kind: PanelKind | None = None) -> list[WeaponRowRead]:
    """Weapon cards whose stat row is on screen, top to bottom. A card scrolled
    so that only part of it shows is reported with clipped=True."""
    kind = classify(frame) if kind is None else kind
    if kind not in WEAPON_KINDS:
        return []
    rows: list[WeaponRowRead] = []
    content_top = CONTENT_REGION[1]
    cards = [
        (strip_top, cells)
        for strip_top, _ in header_strips(frame)
        if len(cells := header_cells(frame, strip_top)) >= 6
    ]
    for index, (strip_top, cells) in enumerate(cards):
        value_y = strip_top + VALUE_OFFSET_Y

        def value(cell: tuple[int, int]) -> Region:
            return (
                cell[0] + CELL_INSET,
                value_y,
                cell[1] - cell[0] - 2 * CELL_INSET,
                VALUE_H,
            )

        span = glyphs.read_span(frame, value(cells[1]))
        text = glyphs.read(frame, value(cells[1])).text
        ammo = glyphs.read_int(frame, value(cells[6])) if len(cells) >= 7 else None
        rows.append(
            WeaponRowRead(
                index=index,
                categories=_categories(frame, strip_top),
                level=glyphs.read_int(frame, value(cells[0])),
                range_min=span[0] if span else None,
                range_max=span[1] if span else None,
                map_weapon=text == "MAP",
                power=glyphs.read_int(frame, value(cells[2])),
                en_cost=glyphs.read_int(frame, value(cells[3])),
                hit_pct=glyphs.read_percent(frame, value(cells[4])),
                crit_pct=glyphs.read_percent(frame, value(cells[5])),
                ammo=ammo,
                has_ammo_column=len(cells) >= 7,
                name_region=(
                    NAME_REGION_X[0],
                    strip_top + NAME_OFFSET_Y,
                    NAME_REGION_X[1],
                    NAME_H,
                ),
                note_region=_note_region(frame, strip_top),
                clipped=strip_top + NAME_OFFSET_Y < content_top,
            )
        )
    return rows


def _bar_top(
    frame: np.ndarray, hue: tuple[int, int], x: tuple[int, int]
) -> tuple[int, int] | None:
    y0, y1 = BAR_SEARCH_Y
    hsv = cv2.cvtColor(frame[y0:y1, x[0] : x[0] + x[1]], cv2.COLOR_BGR2HSV)
    mask = (
        (hsv[:, :, 0] > hue[0])
        & (hsv[:, :, 0] < hue[1])
        & (hsv[:, :, 1] > 120)
        & (hsv[:, :, 2] > 150)
    )
    runs = _colour_runs(mask.sum(1), y0, BAR_MIN_PIXELS)
    return runs[0] if runs else None


def read_basic_view(frame: np.ndarray, kind: PanelKind | None = None) -> BasicView | None:
    """The 基本資訊 overview, or None when that view is not open."""
    kind = classify(frame) if kind is None else kind
    if kind not in BASIC_KINDS:
        return None
    hp_bar = _bar_top(frame, HP_HUE, BAR_X)
    en_bar = _bar_top(frame, EN_HUE, BAR_X)
    sp_bar = _bar_top(frame, SP_HUE, SP_BAR_X)

    def vital(bar: tuple[int, int] | None, x: tuple[int, int], offset: int) -> int | None:
        if bar is None:
            return None
        return glyphs.read_int(frame, (x[0], bar[0] + offset, x[1], VITAL_H))

    faction = None
    if en_bar is not None:
        patch = glyphs.crop(
            frame,
            (
                FACTION_REGION[0],
                en_bar[1] + FACTION_OFFSET_Y,
                FACTION_REGION[2],
                FACTION_REGION[3],
            ),
        )
        if patch.size:
            blue, _, red = patch.reshape(-1, 3).mean(0)
            faction = ENEMY if red > blue + 20 else ALLY if blue > red + 20 else None

    mp = glyphs.read_fraction(frame, MP_REGION, ink=Ink.LIGHT)
    badges = _match_positions(
        frame, "badge_chance_step.png", CS_BADGE_REGION, CS_BADGE_THRESHOLD, CS_BADGE_MIN_GAP
    )
    return BasicView(
        max_hp=vital(hp_bar, VITAL_VALUE_X, VITAL_OFFSET_Y),
        en_max=vital(en_bar, VITAL_VALUE_X, VITAL_OFFSET_Y),
        move_range=(
            None
            if en_bar is None
            else glyphs.read_int(
                frame, (MOVE_VALUE_X[0], en_bar[1] + MOVE_OFFSET_Y, MOVE_VALUE_X[1], VITAL_H)
            )
        ),
        unit_lv=vital(hp_bar, VITAL_VALUE_X, LV_OFFSET_Y),
        faction=faction,
        pilot_lv=vital(sp_bar, PILOT_VALUE_X, LV_OFFSET_Y),
        pilot_sp=vital(sp_bar, PILOT_VALUE_X, VITAL_OFFSET_Y),
        mp_current=mp[0] if mp else None,
        mp_max=mp[1] if mp else None,
        chance_step_badges=len(badges),
    )
