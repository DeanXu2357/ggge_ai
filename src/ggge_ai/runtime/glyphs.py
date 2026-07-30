"""Segment-then-classify glyph reading for the game's numeric panel fields.

The 單位詳情 / 單位設置詳情 panels render numbers as high-contrast text on a
flat field, so a column-projection split gives clean glyph atoms and each atom
is classified against templates cropped from fixtures. Templates are
height-normalised, so one set covers every on-screen size of the same face.

Two pitfalls shape the pipeline. Adjacent digits sometimes touch while a '%'
always splits into two blobs, so atoms are over-split at a fixed width limit
and regrouped by a scoring pass that may merge up to three of them. And the
panel writes an ability-granted delta into the same slot as the absolute value
(blue, '+' prefixed) and marks buffed absolutes with an arrow, so callers that
want a stat must go through read_stat and honour StatReading.delta -- a delta
read as an absolute silently poisons the sandbox.

A field below the ink-contrast gate reads as empty, never guessed: that is also
what a mid-animation cross-fade looks like, and half-faded text must not be
mistaken for a number.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import cv2
import numpy as np

TEMPLATE_ROOT = Path(__file__).resolve().parents[3] / "assets" / "templates" / "glyphs"

CANON_H = 32
BOX_H = 48
LINE_TOP = 8

MIN_CONTRAST = 45
INK_RATIO = 0.45
MIN_ATOM_INK = 6
MAX_ATOM_GAP = 1
SPLIT_RATIO = 0.72
MERGE_RATIO = 1.35
MIN_SCORE = 0.72
GROUP_GATE = 0.62
ALIGN_SHIFT = 2
WIDTH_TOLERANCE = (0.62, 1.6)

_FILENAME_CHARS = {
    "minus": "-",
    "percent": "%",
    "plus": "+",
    "slash": "/",
    "comma": ",",
    "arrow": "▲",
    "letter-m": "M",
    "letter-a": "A",
    "letter-p": "P",
}
ARROW = "▲"


class Ink(StrEnum):
    DARK = "dark"
    LIGHT = "light"


Region = tuple[int, int, int, int]


@dataclass(frozen=True)
class Glyph:
    char: str
    image: np.ndarray


@dataclass(frozen=True)
class Reading:
    text: str
    confidence: float

    @property
    def digits(self) -> str:
        return "".join(c for c in self.text if c.isdigit())


@dataclass(frozen=True)
class StatReading:
    """One value slot of a stat column.

    delta=True means the panel showed an ability contribution ('+N'), not the
    stat: value is that contribution and must not be fed to the sandbox as an
    absolute. buffed=True is the arrow marker on an absolute value.
    """

    value: int | None
    delta: bool = False
    buffed: bool = False
    text: str = ""
    confidence: float = 0.0

    @property
    def absolute(self) -> int | None:
        return None if self.delta else self.value


@dataclass(frozen=True)
class _Field:
    mask: np.ndarray
    line_h: int
    line_top: int
    atoms: tuple[tuple[int, int], ...]


@functools.cache
def load_set(name: str) -> tuple[Glyph, ...]:
    root = TEMPLATE_ROOT / name
    glyphs: list[Glyph] = []
    for path in sorted(root.glob("*.png")):
        stem = path.stem.split("__")[0]
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            continue
        glyphs.append(Glyph(char=_FILENAME_CHARS.get(stem, stem), image=image))
    if not glyphs:
        raise FileNotFoundError(f"no glyph templates under {root}")
    return tuple(glyphs)


def crop(frame: np.ndarray, region: Region) -> np.ndarray:
    x, y, w, h = region
    return frame[max(y, 0) : y + h, max(x, 0) : x + w]


def binarize(patch: np.ndarray, ink: Ink = Ink.DARK) -> np.ndarray | None:
    """Ink mask, or None when the field carries no ink worth reading.

    Background is the median (these fields are mostly background, so it is
    stable) and foreground the darkest median-filtered pixel: a percentile
    would miss a lone thin glyph in a wide cell, whose ink is 2% of the area.
    The red channel stands in for luminance because buffed values render blue,
    where grey contrast alone thins the stroke enough to lose glyph identity.
    """
    if patch.size == 0:
        return None
    gray = patch[:, :, 2]
    if ink is Ink.LIGHT:
        gray = 255 - gray
    background = float(np.median(gray))
    foreground = float(cv2.medianBlur(gray, 3).min())
    if background - foreground < MIN_CONTRAST:
        return None
    return (gray.astype(np.int32) < background - INK_RATIO * (background - foreground)).astype(
        np.uint8
    )


def _blobs(mask: np.ndarray) -> list[list[int]]:
    profile = mask.sum(0)
    runs: list[list[int]] = []
    start: int | None = None
    for index, value in enumerate(profile):
        if value > 0 and start is None:
            start = index
        elif value == 0 and start is not None:
            runs.append([start, index - 1])
            start = None
    if start is not None:
        runs.append([start, len(profile) - 1])
    merged: list[list[int]] = []
    for run in runs:
        if merged and run[0] - merged[-1][1] - 1 <= MAX_ATOM_GAP:
            merged[-1][1] = run[1]
        else:
            merged.append(run)
    return [run for run in merged if mask[:, run[0] : run[1] + 1].sum() >= MIN_ATOM_INK]


def _split(mask: np.ndarray, left: int, right: int, limit: int) -> list[tuple[int, int]]:
    if right - left + 1 <= limit:
        return [(left, right)]
    profile = mask[:, left : right + 1].sum(0)
    low, high = int(len(profile) * 0.25), int(len(profile) * 0.75)
    if high <= low:
        return [(left, right)]
    cut = low + int(np.argmin(profile[low:high]))
    return _split(mask, left, left + cut - 1, limit) + _split(mask, left + cut, right, limit)


def _field(patch: np.ndarray, ink: Ink) -> _Field | None:
    mask = binarize(patch, ink)
    if mask is None:
        return None
    blobs = _blobs(mask)
    if not blobs:
        return None
    extents = []
    for left, right in blobs:
        ys = np.where(mask[:, left : right + 1].any(1))[0]
        extents.append((int(ys.max() - ys.min() + 1), int(ys.min())))
    line_h, line_top = max(extents)
    if line_h < 8:
        return None
    limit = max(4, round(line_h * SPLIT_RATIO))
    atoms: list[tuple[int, int]] = []
    for left, right in blobs:
        atoms.extend(_split(mask, left, right, limit))
    return _Field(mask=mask, line_h=line_h, line_top=line_top, atoms=tuple(atoms))


def _atom_image(field: _Field, left: int, right: int) -> np.ndarray | None:
    column = field.mask[:, left : right + 1]
    ys = np.where(column.any(1))[0]
    if len(ys) == 0:
        return None
    top, bottom = int(ys.min()), int(ys.max())
    scale = CANON_H / field.line_h
    width = max(1, round((right - left + 1) * scale))
    height = max(1, round((bottom - top + 1) * scale))
    glyph = cv2.resize(column[top : bottom + 1] * 255, (width, height), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((BOX_H, width), np.uint8)
    offset = LINE_TOP + round((top - field.line_top) * scale)
    offset = max(0, min(BOX_H - 1, offset))
    rows = min(height, BOX_H - offset)
    canvas[offset : offset + rows] = glyph[:rows]
    return canvas


def _similarity(candidate: np.ndarray, template: np.ndarray) -> float:
    width = max(candidate.shape[1], template.shape[1])

    def pad(image: np.ndarray) -> np.ndarray:
        margin = width - image.shape[1]
        return cv2.copyMakeBorder(
            image, 0, 0, margin // 2, margin - margin // 2, cv2.BORDER_CONSTANT, value=0
        )

    a = pad(candidate) > 127
    b = pad(template) > 127
    best = 0.0
    for dy in range(-ALIGN_SHIFT, ALIGN_SHIFT + 1):
        for dx in range(-ALIGN_SHIFT, ALIGN_SHIFT + 1):
            shifted = np.roll(np.roll(b, dy, axis=0), dx, axis=1)
            total = a.sum() + shifted.sum()
            if total == 0:
                continue
            score = 2.0 * np.logical_and(a, shifted).sum() / total
            best = max(best, score)
    return best


def _classify(image: np.ndarray, glyphs: tuple[Glyph, ...]) -> tuple[str, float]:
    best = ("", 0.0)
    for glyph in glyphs:
        ratio = image.shape[1] / glyph.image.shape[1]
        if not WIDTH_TOLERANCE[0] <= ratio <= WIDTH_TOLERANCE[1]:
            continue
        score = _similarity(image, glyph.image)
        if score > best[1]:
            best = (glyph.char, score)
    return best


def read(
    frame: np.ndarray,
    region: Region,
    *,
    ink: Ink = Ink.DARK,
    glyph_set: str = "panel",
    min_score: float = MIN_SCORE,
) -> Reading:
    """Every glyph in `region`, left to right. Empty text when the field holds
    no ink above the contrast gate or when any glyph scores below min_score."""
    field = _field(crop(frame, region), ink)
    if field is None:
        return Reading("", 0.0)
    glyphs = load_set(glyph_set)
    count = len(field.atoms)
    best: list[tuple[float, list[tuple[str, float]]] | None] = [None] * (count + 1)
    best[count] = (0.0, [])
    for index in range(count - 1, -1, -1):
        for span in (1, 2, 3):
            if index + span > count or best[index + span] is None:
                continue
            left, right = field.atoms[index][0], field.atoms[index + span - 1][1]
            if right - left + 1 > MERGE_RATIO * field.line_h:
                break
            image = _atom_image(field, left, right)
            if image is None:
                continue
            char, score = _classify(image, glyphs)
            tail = best[index + span]
            assert tail is not None
            value = (score - GROUP_GATE) + tail[0]
            if best[index] is None or value > best[index][0]:
                best[index] = (value, [(char, score)] + tail[1])
    head = best[0]
    if head is None or not head[1]:
        return Reading("", 0.0)
    confidence = min(score for _, score in head[1])
    if confidence < min_score:
        return Reading("", confidence)
    return Reading("".join(char for char, _ in head[1]), confidence)


def read_int(frame: np.ndarray, region: Region, **kwargs) -> int | None:
    text = read(frame, region, **kwargs).text
    return int(text) if text.isdigit() else None


def read_stat(frame: np.ndarray, region: Region, **kwargs) -> StatReading:
    reading = read(frame, region, **kwargs)
    text = reading.text
    delta = text.startswith("+")
    buffed = text.startswith(ARROW)
    body = text[1:] if delta or buffed else text
    value = int(body) if body.isdigit() else None
    return StatReading(
        value=value,
        delta=delta,
        buffed=buffed,
        text=text,
        confidence=reading.confidence,
    )


def read_percent(frame: np.ndarray, region: Region, **kwargs) -> int | None:
    """An `N%` field. The '%' must be present: a bare number in a percent slot
    means the region caught something other than its field."""
    text = read(frame, region, **kwargs).text
    if not text.endswith("%"):
        return None
    body = text[:-1]
    return int(body) if body.isdigit() else None


def read_span(frame: np.ndarray, region: Region, **kwargs) -> tuple[int, int] | None:
    """A `k-m` reach band; a lone `n` reads as (n, n). None for anything else,
    including the literal MAP that map weapons print in the same slot."""
    text = read(frame, region, **kwargs).text
    if text.isdigit():
        return int(text), int(text)
    parts = text.split("-")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        return None
    return int(parts[0]), int(parts[1])


def read_fraction(frame: np.ndarray, region: Region, **kwargs) -> tuple[int, int] | None:
    text = read(frame, region, **kwargs).text
    parts = text.split("/")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        return None
    return int(parts[0]), int(parts[1])
