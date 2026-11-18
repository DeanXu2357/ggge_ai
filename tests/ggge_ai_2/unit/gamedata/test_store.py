"""The store writes and reads one datamine stamp (issue #92).

The suite needs a database. Set GGGE_DATABASE_URL to run it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg
import pytest

from ggge_ai_2.gamedata.normalize import Dump, normalize, raw_rows
from ggge_ai_2.gamedata.records import Catalog
from ggge_ai_2.gamedata.store import Store, database_url

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "datamine"
STAMP = "test-202609010310"
HOLDING_STAMP = "test-holding-202609010310"
ZEONG = 1001003000
AMURO = 1001000100
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
        opened.write_stamp(rows, raw)
        yield opened
        opened.delete_stamp(STAMP)


@pytest.fixture
def connection():
    with psycopg.connect(database_url(), autocommit=True) as opened:
        yield opened


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


def test_the_catalog_of_the_read_rows_equals_the_catalog_of_the_written_rows(store, rows):
    assert Catalog.from_rows(store.read_rows(STAMP)) == Catalog.from_rows(rows)


def test_the_read_rows_carry_the_records_of_the_fixture(store):
    catalog = Catalog.from_rows(store.read_rows(STAMP))

    assert catalog.unit(ZEONG).name == "Zeong"
    assert catalog.pilot(AMURO).stats["ranged"].base == 126
    assert catalog.supporter_rate(100, 3) == 14000


def test_a_stamp_that_the_store_does_not_hold_is_no_rows(store):
    with pytest.raises(LookupError):
        store.read_rows("no-such-stamp")


def test_the_constant_tables_hold_the_growth_model(store, connection):
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM level_curve")
        levels = cursor.fetchone()[0]
        cursor.execute("SELECT cap FROM rarity_level_cap WHERE rarity = 4")
        cap = cursor.fetchone()[0]

    assert levels > 0
    assert cap > 0


def test_a_delete_of_the_stamp_clears_the_holding_rows(connection):
    other = normalize(HOLDING_STAMP, Dump.read(FIXTURES))
    with Store() as store:
        store.write_stamp(other, [])
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO holding (stamp, unit_id, level, pilot_id, pilot_level)"
                " VALUES (%s, %s, %s, %s, %s)",
                (HOLDING_STAMP, ZEONG, 100, AMURO, 100),
            )

        store.write_stamp(other, [])
        store.delete_stamp(HOLDING_STAMP)

        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM holding WHERE stamp = %s", (HOLDING_STAMP,))
            assert cursor.fetchone()[0] == 0
        assert HOLDING_STAMP not in store.stamps()


def test_a_null_skill_and_a_null_ability_reach_the_database_as_null(store, connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pilot_skill WHERE stamp = %s AND payload IS NULL", (STAMP,)
        )
        skills = cursor.fetchone()[0]
        cursor.execute(
            "SELECT count(*) FROM pilot_ability WHERE stamp = %s AND payload IS NULL", (STAMP,)
        )
        abilities = cursor.fetchone()[0]

    assert skills == 2
    assert abilities == 3


def test_the_growth_tables_come_from_the_seed_migration(store):
    tables = store.read_growth_tables()

    assert sorted(tables.level_curve) == list(range(1, 101))
    assert sorted(tables.limit_break_rate_percent) == [0, 1, 2, 3]
    assert sorted(tables.rarity_level_cap) == [1, 2, 3, 4, 5]
