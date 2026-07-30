"""Glyph reader pinned to hand-transcribed panel fixture fields.

Every expected string here was read off the fixture image by eye, column by
column. A failure means either the reader regressed or the glyph templates were
rebuilt from different crops -- not that the transcription is negotiable.
"""

from __future__ import annotations

import functools
from pathlib import Path

import cv2
import pytest

from ggge_ai.runtime import glyphs

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "vision"

SIDEBAR_X = 596
STAGE_UNIT_ROWS = (254, 302, 350, 398, 446, 494)
STAGE_PILOT_ROWS = (600, 648, 696, 744, 792, 840)


@functools.cache
def frame(name: str):
    image = cv2.imread(str(FIXTURES / f"{name}.png"))
    assert image is not None, name
    return image


def sidebar(name: str, rows) -> list[str]:
    image = frame(name)
    return [glyphs.read_stat(image, (SIDEBAR_X, y, 148, 32)).text for y in rows]


@pytest.mark.parametrize(
    ("name", "unit", "pilot"),
    [
        (
            "stage_panels/enemy_detail_weapons_gearadoga",
            ["29265", "424", "4", "4078", "3637", "4877"],
            ["326", "326", "292", "327", "281", "15"],
        ),
        (
            "stage_panels/enemy_detail_weapons_unicorngundam",
            ["109440", "750", "4", "8064", "6019", "5455"],
            ["583", "700", "▲690", "525", "▲614", "15"],
        ),
        (
            "stage_panels/ally_detail_weapons_ntgundam",
            ["▲39955", "131", "5", "▲4809", "▲3699", "▲3978"],
            ["113", "112", "79", "141", "92", "15"],
        ),
        (
            "stage_panels/enemy_detail_abilities_kshatriya",
            ["167817", "594", "4", "7206", "9077", "6449"],
            ["491", "477", "+53", "430", "+47", "15"],
        ),
    ],
)
def test_stat_column_text(name, unit, pilot):
    assert sidebar(name, STAGE_UNIT_ROWS) == unit
    assert sidebar(name, STAGE_PILOT_ROWS) == pilot


def test_buffed_absolute_is_a_stat():
    reading = glyphs.read_stat(frame("stage_panels/ally_detail_weapons_ntgundam"), (596, 254, 148, 32))
    assert (reading.value, reading.buffed, reading.delta) == (39955, True, False)
    assert reading.absolute == 39955


def test_ability_delta_is_refused_as_a_stat():
    """The 能力、OP tab writes the ability contribution into the stat slot."""
    reading = glyphs.read_stat(
        frame("stage_panels/ally_detail_abilities_ntgundam"), (596, 254, 148, 32)
    )
    assert (reading.value, reading.delta) == (11010, True)
    assert reading.absolute is None


def test_cross_fade_reads_as_empty_not_as_a_number():
    """kshatriya's weapons tab caught the tab switch mid-fade: the 覺醒值 and
    反應值 slots are half-transparent and must not produce a value."""
    image = frame("stage_panels/enemy_detail_weapons_kshatriya")
    for row in (696, 792):
        reading = glyphs.read_stat(image, (596, row, 148, 32))
        assert reading.text == ""
        assert reading.value is None


@pytest.mark.parametrize(
    ("name", "y", "expected"),
    [
        ("stage_panels/enemy_detail_weapons_gearadoga", 399, ("1", "1-3", "3600", "29", "100%", "0%")),
        ("stage_panels/enemy_detail_weapons_gearadoga", 568, ("1", "1-3", "3200", "25", "100%", "0%")),
        ("stage_panels/enemy_detail_weapons_kshatriya", 739, ("1", "2-4", "3800", "31", "95%", "20%")),
        ("stage_panels/enemy_detail_weapons_unicorngundam", 399, ("1", "1-1", "3500", "25", "110%", "10%")),
        ("roster_panels/unit_weapons_theo_top", 568, ("1", "1-3", "4500", "37", "105%", "10%")),
    ],
)
def test_weapon_row_cells(name, y, expected):
    image = frame(name)
    cells = ((950, 157), (1120, 157), (1291, 190), (1495, 124), (1632, 157), (1803, 189))
    read = tuple(glyphs.read(image, (x, y, w, 38)).text for x, w in cells)
    assert read == expected


def test_map_weapon_range_reads_as_map():
    image = frame("roster_panels/unit_weapons_map_icon_nu_gundam")
    assert glyphs.read(image, (1096, 397, 135, 38)).text == "MAP"
    assert glyphs.read_span(image, (1096, 397, 135, 38)) is None


def test_ammunition_column_reads_a_lone_thin_digit():
    """A '1' is 2% of that cell's area: the ink gate must not call it empty."""
    image = frame("roster_panels/unit_weapons_map_icon_nu_gundam")
    assert glyphs.read_int(image, (1859, 397, 133, 38)) == 1


def test_mp_fraction_is_light_ink():
    image = frame("stage_panels/ally_detail_basicinfo_ntgundam")
    assert glyphs.read_fraction(image, (1780, 608, 95, 44), ink=glyphs.Ink.LIGHT) == (0, 12)


def test_percent_field_requires_the_sign():
    image = frame("stage_panels/enemy_detail_weapons_gearadoga")
    assert glyphs.read_percent(image, (1632, 399, 157, 38)) == 100
    assert glyphs.read_percent(image, (1291, 399, 190, 38)) is None


def test_blank_field_reads_as_none():
    image = frame("stage_panels/enemy_detail_weapons_gearadoga")
    assert glyphs.read(image, (1000, 900, 150, 32)).text == ""
    assert glyphs.read_int(image, (1000, 900, 150, 32)) is None


def test_every_template_char_is_known():
    chars = {glyph.char for glyph in glyphs.load_set("panel")}
    assert chars == set("0123456789") | {"-", "%", "+", "/", "▲", "M", "A", "P"}
