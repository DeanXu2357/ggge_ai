"""One holding becomes the engine payload (issue #92).

The suite needs no database: the catalog comes from the recorded datamine
slice in tests/fixtures/datamine.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from ggge_ai.engine.codec import decode_mech, decode_pilot
from ggge_ai.gamedata import growth
from ggge_ai.gamedata.holding import Crew, Holding, assemble, payload
from ggge_ai.gamedata.normalize import Dump, normalize
from ggge_ai.gamedata.records import Catalog, SspRelease
from scripts.load_holding import run

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DATAMINE = FIXTURES / "datamine"
GOLDENS = FIXTURES / "gamedata"
STAMP = "202609010310"

ZEONG = 1001003000
ZEONG_EX = 1001003050
GUNDAM = 1001000100
AMURO = 1001000100
AMURO_R = 1001000101
KAI = 1001000200
BRIGHT = 1001000150

ZEONG_BASE = [
    "--stamp", STAMP,
    "--from-dump", str(DATAMINE),
    "--unit", str(ZEONG),
    "--level", "100",
    "--limit-break", "3",
    "--mech-sp",
    "--mech-ssp",
    "--weapon-level", "5",
    "--pilot", str(AMURO),
    "--pilot-level", "100",
]

ZEONG_ARGV = [
    *ZEONG_BASE,
    "--supporter", str(BRIGHT),
    "--supporter-level", "100",
    "--supporter-limit-break", "3",
]


@pytest.fixture(scope="module")
def catalog():
    return Catalog.from_rows(normalize(STAMP, Dump.read(DATAMINE)))


def golden(name: str) -> dict:
    return json.loads((GOLDENS / f"{name}.json").read_text(encoding="utf-8"))


def zeong_holding(**changes) -> Holding:
    holding = Holding(
        stamp=STAMP,
        unit_id=ZEONG,
        level=100,
        pilot_id=AMURO,
        pilot_level=100,
        limit_break=3,
        mech_sp=True,
        mech_ssp=True,
        supporter_id=BRIGHT,
        supporter_level=100,
        supporter_limit_break=3,
    )
    return dataclasses.replace(holding, **changes)


def build(catalog: Catalog, holding: Holding):
    supporter = None
    rate = None
    if holding.supporter_id is not None:
        supporter = catalog.supporter(holding.supporter_id)
        rate = catalog.supporter_rate(holding.supporter_level, holding.supporter_limit_break)
    return assemble(
        holding, catalog.unit(holding.unit_id), catalog.pilot(holding.pilot_id), supporter, rate
    )


def test_the_zeong_payload_equals_its_golden(catalog):
    assert payload(build(catalog, zeong_holding())) == golden("zeong_sp_ssp_lb3")


def test_the_gundam_payload_equals_its_golden(catalog):
    holding = Holding(
        stamp=STAMP,
        unit_id=GUNDAM,
        level=50,
        pilot_id=KAI,
        pilot_level=30,
        weapon_level=3,
    )

    built = payload(build(catalog, holding))

    assert built == golden("gundam_plain")
    assert built["crew"] is None


def test_the_zeong_ex_payload_equals_its_golden(catalog):
    holding = Holding(
        stamp=STAMP,
        unit_id=ZEONG_EX,
        level=100,
        pilot_id=AMURO_R,
        pilot_level=100,
        limit_break=3,
    )

    built = payload(build(catalog, holding))

    assert built == golden("zeong_ex_lb3")
    assert built["mech"]["hp"] == 100478


def test_the_ssp_addition_and_the_limit_break_raise_the_hit_points(catalog):
    assert build(catalog, zeong_holding()).mech.hp == 96479
    assert build(catalog, zeong_holding(limit_break=0)).mech.hp == 68914


def test_the_ssp_weapon_comes_last_and_carries_its_enhancements(catalog):
    mech = build(catalog, zeong_holding()).mech
    barrel = catalog.unit(ZEONG).weapons[1]

    assert [weapon.name for weapon in mech.weapons] == [
        "Head Mega Particle Cannon",
        "5-Barrel Arm Mega Particle Cannon",
        "All-Range Attack",
        "All-Range Attack SSP",
    ]
    assert mech.weapons[1].power == float(
        growth.weapon_value(barrel.power, barrel.growth[5].power_rate) + 350
    )
    assert mech.weapons[1].power == 4190.0
    ssp = mech.weapons[3]
    assert (ssp.power, ssp.en_cost, ssp.range_min, ssp.range_max) == (5880.0, 54, 2, 5)
    assert ssp.categories == ["awaken"]


def test_a_holding_without_the_ssp_upgrade_keeps_three_weapons(catalog):
    mech = build(catalog, zeong_holding(mech_ssp=False)).mech

    assert len(mech.weapons) == 3
    assert mech.hp == 90071


def test_a_status_up_release_raises_the_movement(catalog):
    unit = catalog.unit(ZEONG)
    release = SspRelease(
        core_level=20,
        sort_order=1,
        kind="status_up",
        target_id=1,
        payload={"id": 1, "unit_status_type_index": 6, "effect_value": 1},
    )
    raised = dataclasses.replace(unit, releases=(*unit.releases, release))

    holding = zeong_holding(supporter_id=None)
    plain = assemble(holding, unit, catalog.pilot(AMURO), None, None)
    grown = assemble(holding, raised, catalog.pilot(AMURO), None, None)

    assert grown.mech.move_range == plain.mech.move_range + 1


def test_a_level_above_the_cap_gives_the_value_at_the_cap(catalog):
    high = Holding(stamp=STAMP, unit_id=GUNDAM, level=100, pilot_id=KAI, pilot_level=30)
    capped = dataclasses.replace(high, level=80)

    assert build(catalog, high).mech == build(catalog, capped).mech


def test_the_sp_upgrade_reads_the_sp_group_and_lifts_the_cap(catalog):
    stats = catalog.unit(ZEONG).stats["hp"]

    assert build(catalog, zeong_holding(level=1, limit_break=0, mech_ssp=False)).mech.hp == 8936
    plain = zeong_holding(level=1, limit_break=0, mech_sp=False, mech_ssp=False)
    assert build(catalog, plain).mech.hp == 8032
    full = zeong_holding(level=100, limit_break=0, mech_sp=False, mech_ssp=False)
    assert build(catalog, full).mech.hp == growth.level_value(stats.base, stats.max, 90)


def test_an_ult_unit_takes_no_limit_break(catalog):
    unit = dataclasses.replace(catalog.unit(ZEONG), ult=True)
    holding = zeong_holding(supporter_id=None)

    starred = assemble(holding, unit, catalog.pilot(AMURO), None, None)
    plain = assemble(
        dataclasses.replace(holding, limit_break=0), unit, catalog.pilot(AMURO), None, None
    )

    assert starred.mech.hp == plain.mech.hp


@pytest.mark.parametrize(
    "changes",
    [
        {"mech_sp": False},
        {"limit_break": 4},
        {"weapon_level": 6},
        {"level": 0},
        {"pilot_level": 0},
    ],
)
def test_a_holding_outside_the_model_is_no_payload(catalog, changes):
    with pytest.raises(ValueError):
        build(catalog, zeong_holding(**changes))


def test_a_support_crew_without_its_rate_is_no_payload(catalog):
    with pytest.raises(ValueError):
        assemble(zeong_holding(), catalog.unit(ZEONG), catalog.pilot(AMURO), None, 14000)


def test_the_ssp_upgrade_needs_a_unit_that_holds_ssp_stats(catalog):
    holding = Holding(
        stamp=STAMP,
        unit_id=ZEONG_EX,
        level=100,
        pilot_id=AMURO_R,
        pilot_level=100,
        mech_sp=True,
        mech_ssp=True,
    )

    with pytest.raises(ValueError):
        build(catalog, holding)


def test_an_unknown_attack_attribute_is_no_weapon(catalog):
    unit = catalog.unit(ZEONG)
    broken = dataclasses.replace(unit.weapons[0], attack_attr=9)
    changed = dataclasses.replace(unit, weapons=(broken, *unit.weapons[1:]))

    with pytest.raises(ValueError, match="unknown attack attribute"):
        assemble(zeong_holding(supporter_id=None), changed, catalog.pilot(AMURO), None, None)


def test_the_attack_attributes_five_and_six_pair_awaken_by_hypothesis(catalog):
    unit = catalog.unit(ZEONG)
    holding = zeong_holding(supporter_id=None, mech_ssp=False)

    def categories(attack_attr: int) -> list[str]:
        weapon = dataclasses.replace(unit.weapons[0], attack_attr=attack_attr)
        changed = dataclasses.replace(unit, weapons=(weapon, *unit.weapons[1:]))
        built = assemble(holding, changed, catalog.pilot(AMURO), None, None)
        return built.mech.weapons[0].categories

    assert categories(5) == ["ranged", "awaken"]
    assert categories(6) == ["melee", "awaken"]


def test_the_pilot_follows_the_level_curve_of_its_rarity(catalog):
    record = catalog.pilot(AMURO)
    cap = growth.level_cap(record.rarity)

    pilot = build(catalog, zeong_holding()).pilot

    for stat in ("ranged", "melee", "awaken", "defense", "reaction"):
        row = record.stats[stat]
        assert getattr(pilot, stat) == float(growth.level_value(row.base, row.max, cap))
    assert pilot.sp == 0


def test_the_support_crew_bonus_follows_its_growth_row(catalog):
    assert build(catalog, zeong_holding()).crew == Crew(hp=2800, attack=420)
    low = zeong_holding(supporter_level=1, supporter_limit_break=0)
    assert build(catalog, low).crew == Crew(hp=400, attack=60)


def test_the_payload_decodes_back_into_the_engine_state(catalog):
    assembled = build(catalog, zeong_holding())
    wire = payload(assembled)

    assert decode_mech(wire["mech"]) == assembled.mech
    assert decode_pilot(wire["pilot"]) == assembled.pilot


def test_the_script_reads_a_dump_and_prints_the_golden(catalog):
    assert run(ZEONG_ARGV) == golden("zeong_sp_ssp_lb3")


@pytest.mark.parametrize(
    "flags",
    [
        ["--supporter", str(BRIGHT)],
        ["--supporter", str(BRIGHT), "--supporter-level", "100"],
        ["--supporter", str(BRIGHT), "--supporter-limit-break", "3"],
        ["--supporter-level", "100"],
        ["--supporter-limit-break", "3"],
        ["--supporter-level", "100", "--supporter-limit-break", "3"],
    ],
)
def test_the_support_crew_flags_travel_together(flags):
    with pytest.raises(SystemExit):
        run([*ZEONG_BASE, *flags])
