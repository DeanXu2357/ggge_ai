"""Semantic contract of the detail-modal parser (M3a).

Read accuracy is pinned by tests/fixtures/vision/panels/; these tests
cover the modal gate and the panel-to-spec conversion logic.
"""

from __future__ import annotations

import numpy as np

from ggge_ai.battle import panels
from ggge_ai.battle.panels import UnitStats, WeaponRow


def _stats(**overrides):
    base = dict(
        hp=51349,
        en=377,
        move_range=4,
        unit_attack=3586,
        unit_defense=3939,
        unit_mobility=3219,
        pilot_shooting=168,
        pilot_melee=170,
        pilot_awakening=179,
        pilot_defense=204,
        pilot_reaction=223,
        sp=15,
    )
    base.update(overrides)
    return UnitStats(**base)


def _row(**overrides):
    base = dict(
        kind="melee",
        level=1,
        range_min=1,
        range_max=2,
        power=3500,
        en_cost=27,
        hit_pct=100,
        crit_pct=5,
    )
    base.update(overrides)
    return WeaponRow(**base)


def test_parsers_decline_without_modal() -> None:
    frame = np.zeros((1080, 2340, 3), np.uint8)
    assert panels.parse_unit_stats(frame) is None
    assert panels.parse_weapon_rows(frame) == []


def test_to_unit_spec_maps_fields() -> None:
    spec, assumptions = panels.to_unit_spec(_stats(), [_row()])
    assert assumptions == []
    assert spec.max_hp == 51349
    assert spec.en_max == 377
    assert spec.move_range == 4
    assert spec.unit_attack == 3586.0
    assert spec.mobility == 3219.0
    assert spec.reaction == 223.0
    assert spec.pilot_shooting == 168.0
    assert spec.pilot_melee == 170.0
    assert spec.pilot_attack is None
    assert len(spec.weapons) == 1
    weapon = spec.weapons[0]
    assert weapon.power == 3500.0
    assert (weapon.range_min, weapon.range_max) == (1, 2)
    assert weapon.en_cost == 27


def test_to_unit_spec_drops_unreadable_weapon_with_assumption() -> None:
    spec, assumptions = panels.to_unit_spec(_stats(), [_row(power=None), _row(power=3200)])
    assert len(spec.weapons) == 1
    assert spec.weapons[0].power == 3200.0
    assert any("row dropped" in a for a in assumptions)


def test_to_unit_spec_assumes_range_when_unread() -> None:
    spec, assumptions = panels.to_unit_spec(_stats(), [_row(range_min=None, range_max=None)])
    assert (spec.weapons[0].range_min, spec.weapons[0].range_max) == (1, 1)
    assert any("assuming 1-1" in a for a in assumptions)


def test_pilot_attack_for_kind_selection() -> None:
    spec, _ = panels.to_unit_spec(_stats(), [])
    assert panels.pilot_attack_for(spec, "shooting") == 168.0
    assert panels.pilot_attack_for(spec, "melee") == 170.0
    assert panels.pilot_attack_for(spec, None) is None


def test_pilot_attack_for_falls_back_when_stat_unread() -> None:
    spec, _ = panels.to_unit_spec(_stats(pilot_shooting=None), [])
    assert panels.pilot_attack_for(spec, "shooting") is None
