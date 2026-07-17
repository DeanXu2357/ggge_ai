"""單位設置詳情 modal parser: unit/pilot stats and weapon rows.

The left stat column is identical on all three tabs (組合資訊 / 武裝、技能 /
能力、OP), so parse_unit_stats works whichever tab is active; weapon rows
need the 武裝、技能 tab and are located by probing each card's LV/RANGE
header strip at a fixed pitch. All numbers are dark-on-light modal digits
(the "modal" glyph font, invert=True); stat values buffed by abilities
render blue with ▲▲ arrows and read identically (measured 12/12 on the
20260705-154019 capture).
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ..content.kit import UnitStats, WeaponRow
from ..vision import digits
from .vision import _cached_template, _crop, is_unit_detail_modal

_ELEMENTS = Path(__file__).resolve().parents[3] / "assets" / "templates" / "elements"

WEAPON_ROW_HEADER_TEMPLATE = _ELEMENTS / "weapon_row_header.png"
BADGE_MELEE_TEMPLATE = _ELEMENTS / "badge_melee.png"
BADGE_SHOOTING_TEMPLATE = _ELEMENTS / "badge_shooting.png"

STAT_VALUE_X = (620, 130)
UNIT_STAT_ROWS_Y = (246, 294, 342, 390, 438, 486)
PILOT_STAT_ROWS_Y = (594, 642, 690, 738, 786, 834)
STAT_ROW_H = 46
STAT_DIGIT_HEIGHT = 30

# first weapon card's header strip starts at y=376; cards repeat every
# 170px. probing stops at the first missing header, so a tab without
# weapon cards (or the wrong tab) parses as zero rows
WEAPON_CARD_BASE_Y = 376
WEAPON_CARD_PITCH = 170
WEAPON_CARD_MAX = 4
WEAPON_HEADER_PROBE = (985, 300)
WEAPON_HEADER_THRESHOLD = 0.8
WEAPON_ROW_DIGIT_HEIGHT = 24
WEAPON_VALUE_OFFSET_Y = 24
WEAPON_COLUMNS = {
    "level": (990, 80),
    "range": (1150, 110),
    "power": (1290, 195),
    "en_cost": (1495, 125),
    "hit_pct": (1630, 160),
    "crit_pct": (1800, 160),
}
BADGE_OFFSET_Y = -74
BADGE_REGION_X = (1840, 170)
BADGE_H = 52
BADGE_THRESHOLD = 0.75


def _read_stat(frame: np.ndarray, row_y: int) -> int | None:
    x, w = STAT_VALUE_X
    return digits.read_number(
        frame,
        (x, row_y, w, STAT_ROW_H),
        digit_height=STAT_DIGIT_HEIGHT,
        font="modal",
        invert=True,
        allow_minus=False,
    )


def parse_unit_stats(frame: np.ndarray) -> UnitStats | None:
    """The left stat column, or None when the detail modal is not open."""
    if not is_unit_detail_modal(frame):
        return None
    unit = [_read_stat(frame, y) for y in UNIT_STAT_ROWS_Y]
    pilot = [_read_stat(frame, y) for y in PILOT_STAT_ROWS_Y]
    return UnitStats(
        hp=unit[0],
        en=unit[1],
        move_range=unit[2],
        unit_attack=unit[3],
        unit_defense=unit[4],
        unit_mobility=unit[5],
        pilot_shooting=pilot[0],
        pilot_melee=pilot[1],
        pilot_awakening=pilot[2],
        pilot_defense=pilot[3],
        pilot_reaction=pilot[4],
        sp=pilot[5],
    )


def _match_score(frame: np.ndarray, template_path: Path, region: tuple[int, int, int, int]) -> float:
    template = _cached_template(str(template_path))
    if template is None:
        return 0.0
    crop = _crop(frame, region)
    if crop.shape[0] < template.shape[0] or crop.shape[1] < template.shape[1]:
        return 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    tgray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    result = cv2.matchTemplate(gray, tgray, cv2.TM_CCOEFF_NORMED)
    return float(result.max())


def _badge_kind(frame: np.ndarray, card_y: int) -> str | None:
    bx, bw = BADGE_REGION_X
    region = (bx, card_y + BADGE_OFFSET_Y, bw, BADGE_H)
    scores = {
        "melee": _match_score(frame, BADGE_MELEE_TEMPLATE, region),
        "shooting": _match_score(frame, BADGE_SHOOTING_TEMPLATE, region),
    }
    kind, best = max(scores.items(), key=lambda kv: kv[1])
    return kind if best >= BADGE_THRESHOLD else None


def parse_weapon_rows(frame: np.ndarray) -> list[WeaponRow]:
    """Visible weapon cards on the 武裝、技能 tab, top to bottom. Rows the
    scroll hides are not probed -- callers record that as an assumption."""
    if not is_unit_detail_modal(frame):
        return []
    rows: list[WeaponRow] = []
    for i in range(WEAPON_CARD_MAX):
        card_y = WEAPON_CARD_BASE_Y + i * WEAPON_CARD_PITCH
        px, pw = WEAPON_HEADER_PROBE
        if _match_score(frame, WEAPON_ROW_HEADER_TEMPLATE, (px, card_y - 4, pw, 36)) < (
            WEAPON_HEADER_THRESHOLD
        ):
            break
        value_y = card_y + WEAPON_VALUE_OFFSET_Y
        common = {"digit_height": WEAPON_ROW_DIGIT_HEIGHT, "font": "modal", "invert": True}

        def field(name: str) -> tuple[int, int, int, int]:
            x, w = WEAPON_COLUMNS[name]
            return (x, value_y, w, 36)

        span = digits.read_span(frame, field("range"), **common)
        rows.append(
            WeaponRow(
                kind=_badge_kind(frame, card_y),
                level=digits.read_number(frame, field("level"), allow_minus=False, **common),
                range_min=span[0] if span else None,
                range_max=span[1] if span else None,
                power=digits.read_number(frame, field("power"), allow_minus=False, **common),
                en_cost=digits.read_number(frame, field("en_cost"), allow_minus=False, **common),
                hit_pct=digits.read_percent(frame, field("hit_pct"), **common),
                crit_pct=digits.read_percent(frame, field("crit_pct"), **common),
            )
        )
    return rows


