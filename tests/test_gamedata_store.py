"""The store writes and reads one datamine stamp (issue #92).

The suite needs a database. Set GGGE_DATABASE_URL to run it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ggge_ai.gamedata.normalize import Dump, normalize, raw_rows
from ggge_ai.gamedata.store import Store

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "datamine"
STAMP = "test-202609010310"
ZEONG = 1001003000
ZEONG_SSP_WEAPON = 100100300090
AMURO = 1001000100
BRIGHT = 1001000150
RAW_SOURCES = ("unit", "weapon", "character", "supporter", "supporter_growth", "stage")

pytestmark = pytest.mark.skipif(
    "GGGE_DATABASE_URL" not in os.environ, reason="GGGE_DATABASE_URL is unset"
)


@pytest.fixture(scope="module")
def rows():
    return normalize(STAMP, Dump.read(FIXTURES))


@pytest.fixture(scope="module")
def raw():
    payloads = {
        name: json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
        for name in RAW_SOURCES
    }
    return [row for name, payload in payloads.items() for row in raw_rows(STAMP, name, payload)]


@pytest.fixture(scope="module")
def store(rows, raw):
    with Store() as opened:
        opened.write_constants()
        opened.write_stamp(rows, raw)
        yield opened
        opened.delete_stamp(STAMP)


def test_the_written_stamp_holds_every_normalized_row(store, rows, raw):
    counts = store.counts(STAMP)

    assert counts["datamine_raw"] == len(raw)
    for table, count in counts.items():
        if table == "datamine_raw":
            continue
        assert count == len(rows.tables[table]), table
    assert STAMP in store.stamps()


def test_a_second_write_of_the_same_stamp_keeps_the_same_counts(store, rows, raw):
    before = store.counts(STAMP)
    store.write_stamp(rows, raw)

    assert store.counts(STAMP) == before


def test_the_unit_record_carries_its_stats_its_cores_and_its_weapons(store):
    unit = store.read_unit(STAMP, ZEONG)

    assert unit.name == "Zeong"
    assert len(unit.stats) == 6
    assert unit.stats["hp"].base == 8032
    assert unit.ssp_stats["hp"].max == 4577
    assert [(item.core_level, item.sort_order, item.kind) for item in unit.releases] == [
        (0, 1, "ability_change"),
        (1, 1, "weapon_change"),
        (1, 2, "weapon_enhance"),
        (5, 1, "terrain"),
        (10, 1, "weapon_effect"),
        (10, 2, "weapon_enhance"),
    ]
    assert len(unit.weapons) == 4
    ssp = next(weapon for weapon in unit.weapons if weapon.id == ZEONG_SSP_WEAPON)
    assert ssp.is_ssp is True
    assert ssp.growth[5].power_rate == 120


def test_a_unit_that_the_stamp_does_not_hold_is_no_record(store):
    with pytest.raises(LookupError):
        store.read_unit(STAMP, 1)


def test_the_pilot_record_carries_its_five_stats(store):
    pilot = store.read_pilot(STAMP, AMURO)

    assert pilot.name == "Amuro Ray"
    assert len(pilot.stats) == 5
    assert pilot.stats["ranged"].base == 126


def test_the_support_crew_record_and_its_growth_rate(store):
    crew = store.read_supporter(STAMP, BRIGHT)

    assert crew.max_hp_addition == 2000
    assert crew.max_attack_addition == 300
    assert store.supporter_rate(100, 3) == 14000
