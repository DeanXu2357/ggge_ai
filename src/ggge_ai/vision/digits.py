"""Deterministic template-digit OCR for the game's HUD numbers.

Glyph templates live in assets/templates/digits/<font>/ and were cropped
from full-resolution PNG captures only (JPEG artifacts flip pixel-level
classifications). Multiple size variants per char are allowed
(`6.png`, `6_s.png`, `6_b.png` all map to '6'); every variant's body was
scaled to CANON_H at extraction, so a caller only needs the on-screen
digit height of its region (a fixed per-region property).

Reading pipeline, tuned on a 15-case corpus sweep (2026-07-12):
1. rescale the band so digits land at CANON_H, then TM_CCOEFF_NORMED with
   every glyph variant -- sliding match, not component segmentation,
   because damage numbers overlap the white HP bar where a white mask
   cannot separate glyph from background;
2. score-priority NMS on horizontal overlap;
3. small glyphs (minus/percent) must sit on the digit line -- their tiny
   templates otherwise fire on edge noise and label strokes. The slash is
   exempt from their raised gate: read_fraction's digit/digit format
   already constrains it, and the translucent header dims it to 0.75 on
   busy map backgrounds;
3b. only the longest contiguous glyph run survives: one number's glyphs
   advance by 20-30px at CANON_H, while stray hits on screen furniture
   (the header bar's bright edge line matches '4' at 0.757) sit far from
   the digit run, so a start-to-start gap above 1.25*CANON_H splits them
   off;
4. each digit position is re-checked by masked TM_SQDIFF_NORMED over a
   small alignment neighborhood: correlation confuses round digits (6/8)
   across background contexts, but background pixels are masked out of
   the SQDIFF so glyph identity is decided on glyph pixels alone. The
   SQDIFF verdict only overrides the correlation winner when it is
   decisive (beats the winner's own SQDIFF by a clear margin) -- razor
   thin SQDIFF differences are noise while the correlation winner
   carries real evidence;
5. '-' is only legal leading (and only when the caller allows negatives),
   '%' only trailing.

A reading below the score gate yields value=None: this reader never
guesses. The inverse does not hold -- dark map texture can push a stray
single glyph over the correlation gate (the known TM_CCOEFF_NORMED
uniform-region hazard), so callers must anchor on panel presence before
trusting a read from a region that might not be showing its panel.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

CANON_H = 32
TEMPLATE_ROOT = Path(__file__).resolve().parents[3] / "assets" / "templates" / "digits"

_NAME_TO_CHAR = {"minus": "-", "slash": "/", "percent": "%"}
_MIN_SCORE = 0.72
_SMALL_GLYPH_BOOST = 0.08
_LINE_TOLERANCE = 0.25
_ALIGN_SEARCH = 3
_RERANK_MARGIN = 0.75
_GAP_LIMIT = int(CANON_H * 1.25)


@dataclass(frozen=True)
class GlyphMatch:
    char: str
    x: int
    score: float


@dataclass
class DigitReading:
    text: str
    value: int | None
    confidence: float
    glyphs: list[GlyphMatch]


@dataclass(frozen=True)
class _Glyph:
    char: str
    image: np.ndarray
    mask: np.ndarray


@functools.cache
def _load_glyphs(font: str) -> tuple[_Glyph, ...]:
    root = TEMPLATE_ROOT / font
    glyphs = []
    for path in sorted(root.glob("*.png")):
        stem = path.stem.split("_")[0]
        char = _NAME_TO_CHAR.get(stem, stem)
        img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        body = (img >= 160).astype(np.uint8) * 255
        mask = cv2.dilate(body, np.ones((3, 3), np.uint8), iterations=2)
        glyphs.append(_Glyph(char=char, image=img, mask=mask))
    if not glyphs:
        raise FileNotFoundError(f"no digit glyphs under {root}")
    return tuple(glyphs)


def _sqdiff_at(band: np.ndarray, cy: float, cx: float, glyph: _Glyph) -> float:
    """Masked SQDIFF of one glyph centered near (cy, cx), minimized over a
    small alignment neighborhood."""
    th, tw = glyph.image.shape
    best = np.inf
    for dy in range(-_ALIGN_SEARCH, _ALIGN_SEARCH + 1):
        for dx in range(-_ALIGN_SEARCH, _ALIGN_SEARCH + 1):
            y0 = int(round(cy - th / 2)) + dy
            x0 = int(round(cx - tw / 2)) + dx
            if y0 < 0 or x0 < 0 or y0 + th > band.shape[0] or x0 + tw > band.shape[1]:
                continue
            window = band[y0 : y0 + th, x0 : x0 + tw]
            value = float(
                cv2.matchTemplate(window, glyph.image, cv2.TM_SQDIFF_NORMED, mask=glyph.mask)[0, 0]
            )
            if np.isfinite(value) and value < best:
                best = value
    return best


def read_text(
    frame: np.ndarray,
    region: tuple[int, int, int, int],
    *,
    digit_height: int,
    font: str = "hud",
    min_score: float = _MIN_SCORE,
    invert: bool = False,
    allow_minus: bool = True,
    interior_minus: bool = False,
) -> DigitReading:
    """Read the glyph string in `region`. digit_height is the on-screen
    pixel height of the digits there; invert reads dark-on-light text
    (the TURN chip, detail-modal fields); allow_minus=False is for fields
    that can never be negative (HP/EN/counters), where a stray dash hit
    must not survive; interior_minus keeps non-leading dashes for reach
    bands like RANGE 1-2."""
    x, y, w, h = region
    crop = frame[y : y + h, x : x + w]
    if crop.size == 0:
        return DigitReading("", None, 0.0, [])
    band = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    if invert:
        band = 255 - band
    scale = CANON_H / digit_height
    band = cv2.resize(
        band, (max(round(band.shape[1] * scale), 1), max(round(band.shape[0] * scale), 1))
    )
    band = cv2.copyMakeBorder(band, 8, 8, 12, 12, cv2.BORDER_REPLICATE)

    glyphs = _load_glyphs(font)
    candidates = []
    for glyph in glyphs:
        if glyph.char == "-" and not allow_minus:
            continue
        th, tw = glyph.image.shape
        if band.shape[0] < th or band.shape[1] < tw:
            continue
        result = cv2.matchTemplate(band, glyph.image, cv2.TM_CCOEFF_NORMED)
        gate = min_score + (_SMALL_GLYPH_BOOST if glyph.char in "-%" else 0.0)
        ys, xs = np.where(result >= gate)
        for yy, xx in zip(ys, xs):
            candidates.append((float(result[yy, xx]), glyph.char, int(xx), int(yy), tw, th))
    candidates.sort(reverse=True)

    kept: list[tuple[float, str, int, int, int, int]] = []
    for score, char, cx, cy, tw, th in candidates:
        center = cx + tw / 2
        if all(
            abs(center - (kx + ktw / 2)) >= max(tw, ktw) * 0.55
            for _, _, kx, _, ktw, _ in kept
        ):
            kept.append((score, char, cx, cy, tw, th))
    kept.sort(key=lambda c: c[2])

    if kept:
        runs: list[list[tuple[float, str, int, int, int, int]]] = [[kept[0]]]
        for item in kept[1:]:
            if item[2] - runs[-1][-1][2] > _GAP_LIMIT:
                runs.append([])
            runs[-1].append(item)
        kept = max(runs, key=len)

    digit_centers = [yy + th / 2 for _, ch, _, yy, _, th in kept if ch.isdigit()]
    if digit_centers:
        line_cy = float(np.median(digit_centers))
        kept = [
            k
            for k in kept
            if k[1].isdigit()
            or k[1] == "/"
            or abs((k[3] + k[5] / 2) - line_cy) <= CANON_H * _LINE_TOLERANCE
        ]

    matches: list[GlyphMatch] = []
    for score, char, cx, cy, tw, th in kept:
        if char.isdigit():
            center_y, center_x = cy + th / 2, cx + tw / 2
            by_char: dict[str, float] = {}
            for glyph in glyphs:
                if not glyph.char.isdigit():
                    continue
                value = _sqdiff_at(band, center_y, center_x, glyph)
                if value < by_char.get(glyph.char, np.inf):
                    by_char[glyph.char] = value
            if by_char:
                incumbent = by_char.get(char, np.inf)
                challenger, challenger_value = min(by_char.items(), key=lambda kv: kv[1])
                if challenger != char and challenger_value < incumbent * _RERANK_MARGIN:
                    char = challenger
        matches.append(GlyphMatch(char=char, x=cx, score=score))

    chars = [m.char for m in matches]
    while not interior_minus and "-" in chars[1:]:
        index = chars.index("-", 1)
        chars.pop(index)
        matches.pop(index)
    while "%" in chars[:-1]:
        index = chars.index("%")
        chars.pop(index)
        matches.pop(index)

    text = "".join(chars)
    confidence = min((m.score for m in matches), default=0.0)
    value: int | None = None
    body = text[1:] if text.startswith("-") else text
    if body and body.isdigit():
        value = int(text)
    return DigitReading(text=text, value=value, confidence=confidence, glyphs=matches)


def read_number(
    frame: np.ndarray,
    region: tuple[int, int, int, int],
    *,
    digit_height: int,
    font: str = "hud",
    min_score: float = _MIN_SCORE,
    invert: bool = False,
    allow_minus: bool = True,
) -> int | None:
    """A plain (optionally negative) integer, or None when the region does
    not read as exactly one number."""
    return read_text(
        frame,
        region,
        digit_height=digit_height,
        font=font,
        min_score=min_score,
        invert=invert,
        allow_minus=allow_minus,
    ).value


def read_fraction(
    frame: np.ndarray,
    region: tuple[int, int, int, int],
    *,
    digit_height: int,
    font: str = "hud",
    min_score: float = _MIN_SCORE,
    invert: bool = False,
) -> tuple[int, int] | None:
    """A `k/m` pair (kill counter, charge counters), or None."""
    reading = read_text(
        frame,
        region,
        digit_height=digit_height,
        font=font,
        min_score=min_score,
        invert=invert,
        allow_minus=False,
    )
    parts = reading.text.split("/")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    return int(parts[0]), int(parts[1])


def read_span(
    frame: np.ndarray,
    region: tuple[int, int, int, int],
    *,
    digit_height: int,
    font: str = "hud",
    min_score: float = _MIN_SCORE,
    invert: bool = False,
) -> tuple[int, int] | None:
    """A `k-m` reach band (weapon RANGE), or None. A single number n reads
    as (n, n)."""
    reading = read_text(
        frame,
        region,
        digit_height=digit_height,
        font=font,
        min_score=min_score,
        invert=invert,
        interior_minus=True,
    )
    if reading.text.isdigit():
        value = int(reading.text)
        return value, value
    parts = reading.text.split("-")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    return int(parts[0]), int(parts[1])


def read_percent(
    frame: np.ndarray,
    region: tuple[int, int, int, int],
    *,
    digit_height: int,
    font: str = "hud",
    min_score: float = _MIN_SCORE,
    invert: bool = False,
) -> int | None:
    """A `NN%` value, or None. The % glyph must be present: a bare number
    in a percent field usually means the region caught something else."""
    reading = read_text(
        frame,
        region,
        digit_height=digit_height,
        font=font,
        min_score=min_score,
        invert=invert,
        allow_minus=False,
    )
    if not reading.text.endswith("%"):
        return None
    digits_part = reading.text[:-1]
    if not digits_part.isdigit() or not digits_part:
        return None
    value = int(digits_part)
    return value if 0 <= value <= 100 else None
