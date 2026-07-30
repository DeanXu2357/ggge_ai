"""Panel readings folded into a UnitIntel, gaps declared rather than papered over."""

from __future__ import annotations

import functools
from pathlib import Path

import cv2
import pytest

from ggge_ai.runtime import panels
from ggge_ai.runtime.panel_text import AbilityText, AbilityTexts, WeaponText
from ggge_ai.sandbox.model import Faction, MoveKind
from ggge_ai.stage.intel_panels import PilotOffence, unit_intel_from_panels

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "vision"


@functools.cache
def frame(name: str):
    image = cv2.imread(str(FIXTURES / f"{name}.png"))
    assert image is not None, name
    return image


def read(name: str):
    image = frame(name)
    kind = panels.classify(image)
    return (
        panels.read_stat_column(image, kind),
        panels.read_basic_view(image, kind),
        panels.read_weapon_rows(image, kind),
    )


def test_stage_weapons_tab_assembles_the_numeric_core():
    column, _, rows = read("stage_panels/enemy_detail_weapons_kshatriya")
    names = ("光束軍刀", "胸部MEGA粒子砲", "感應砲")
    weapons = tuple(
        (row, WeaponText(name=name, matched=True)) for row, name in zip(rows, names, strict=True)
    )
    result = unit_intel_from_panels("kshatriya", column=column, weapons=weapons, pick="melee")
    record = result.record
    assert (record.max_hp, record.en_max, record.move_range) == (167817, 594, 4)
    assert (record.unit_attack, record.unit_defense, record.mobility) == (7206.0, 9077.0, 6449.0)
    assert record.pilot_defense == 430.0
    assert [weapon.name for weapon in record.weapons] == list(names)
    assert record.weapons[0].power == 3500.0
    assert record.weapons[0].en_cost == 25


def test_hit_percent_becomes_an_accuracy_offset():
    """105% on the panel is +5 to the additive hit term the sandbox uses."""
    column, _, rows = read("stage_panels/enemy_detail_weapons_kshatriya")
    weapons = tuple((row, WeaponText(name=f"w{row.index}")) for row in rows)
    record = unit_intel_from_panels("kshatriya", column=column, weapons=weapons).record
    assert [weapon.accuracy for weapon in record.weapons] == [5.0, 5.0, -5.0]


def test_map_weapon_keeps_the_flag_and_declares_the_blast_gap():
    _, _, rows = read("roster_panels/unit_weapons_map_icon_nu_gundam")
    weapons = ((rows[0], WeaponText(name="雙翼狀感應砲")),)
    result = unit_intel_from_panels("nu_gundam", weapons=weapons)
    assert result.record.weapons[0].map_weapon is True
    assert result.record.weapons[0].ammo == 1
    assert "weapon0:map_blast" in result.gaps


def test_pilot_offence_is_reported_unpicked_by_default():
    """The game splits 射擊值/格鬥值/覺醒值; sandbox Unit carries one
    pilot_attack, so the collapse is the caller's call, not the parser's."""
    column, _, _ = read("stage_panels/enemy_detail_weapons_unicorngundam")
    result = unit_intel_from_panels("unicorn", column=column)
    assert result.pilot_offence == PilotOffence(shooting=583, melee=700, awakening=690)
    assert result.record.pilot_attack == 0.0
    assert "pilot_attack:unpicked" in result.gaps


@pytest.mark.parametrize(
    ("pick", "expected"), [("shooting", 583.0), ("melee", 700.0), ("awakening", 690.0)]
)
def test_pilot_offence_pick(pick, expected):
    column, _, _ = read("stage_panels/enemy_detail_weapons_unicorngundam")
    result = unit_intel_from_panels("unicorn", column=column, pick=pick)
    assert result.record.pilot_attack == expected
    assert "pilot_attack:unpicked" not in result.gaps


def test_bad_pick_is_a_programming_error():
    with pytest.raises(ValueError):
        unit_intel_from_panels("unicorn", pick="reaction")


def test_delta_stats_are_refused_and_named():
    column, _, _ = read("stage_panels/ally_detail_abilities_ntgundam")
    result = unit_intel_from_panels("nt_gundam", column=column)
    assert result.record.max_hp == 1
    assert "max_hp:delta" in result.gaps
    assert "unit_attack:delta" in result.gaps
    assert result.record.en_max == 131


def test_basic_view_fills_what_the_stat_column_lacks():
    _, basic, _ = read("stage_panels/ally_detail_basicinfo_ntgundam")
    result = unit_intel_from_panels("nt_gundam", basic=basic)
    assert (result.record.max_hp, result.record.en_max, result.record.move_range) == (39955, 131, 5)
    assert result.record.chance_steps_max == 1
    assert "stat_column" in result.gaps


def test_abilities_map_onto_implemented_flags_only():
    texts = AbilityTexts(
        entries=(
            AbilityText(name="盾牌防禦", owner="unit", effect="shield_defense", magnitude=0.2),
            AbilityText(name="攔截支援", owner="unit", effect="attack_shield"),
            AbilityText(name="攔截減輕", owner="unit", effect="interception_reduction", magnitude=0.3),
            AbilityText(name="支援防禦+1次", owner="pilot", effect="support_defend_charge", magnitude=1),
            AbilityText(name="EN回復", owner="pilot", effect="skill_en_refill", magnitude=50),
            AbilityText(name="複製新人類", owner="pilot", effect=None),
        ),
        unsupported=("自身覺醒值及反應值提升10%",),
    )
    result = unit_intel_from_panels("kshatriya", abilities=texts)
    record = result.record
    assert record.has_shield is True
    assert record.attack_shield is True
    assert record.interception_reduction == 0.3
    assert record.support_defend_charges_max == 1
    assert [(skill.kind, skill.amount) for skill in record.skills] == [
        (MoveKind.SKILL_EN_REFILL, 50.0)
    ]
    assert result.unsupported == ("自身覺醒值及反應值提升10%",)


def test_missing_abilities_is_a_gap_not_a_clean_record():
    result = unit_intel_from_panels("kshatriya")
    assert "abilities" in result.gaps
    assert "weapons" in result.gaps
    assert result.complete is False


def test_record_round_trips_through_the_intel_library():
    column, basic, rows = read("stage_panels/enemy_detail_weapons_gearadoga")
    weapons = tuple((row, WeaponText(name=f"w{row.index}")) for row in rows)
    result = unit_intel_from_panels(
        "geara_doga", column=column, basic=basic, weapons=weapons, pick="shooting"
    )
    unit = result.record.to_unit(Faction.ENEMY)
    assert unit.max_hp == 29265
    assert unit.pilot_attack == 326.0
    assert len(unit.weapons) == 2
