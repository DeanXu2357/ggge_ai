"""情報庫：兩區存取、known 只認畫面、組裝沙盤 Unit、序列化往返。"""

from __future__ import annotations

from ggge_ai.runtime.perceive import Observation
from ggge_ai.engine.contract import ActionKind, Faction
from ggge_ai.stage.intel import (
    IntelPerceiver,
    Intelligence,
    Side,
    SkillIntel,
    UnitIntel,
    WeaponIntel,
    loads,
)
from tests.fixtures.stage_offline import ScriptedPerceiver, battle, frame

BEAM = WeaponIntel(
    name="ビームライフル",
    power=120.0,
    range_min=1,
    range_max=3,
    en_cost=10,
    categories=("shooting",),
    crit_pct=10,
    level=2,
)
MAP_GUN = WeaponIntel(name="メガ粒子砲", power=300.0, range_max=5, map_weapon=True, ammo=2)
REFILL = SkillIntel(kind=ActionKind.SKILL_EN_REFILL, amount=40.0, uses=2)


def unicorn() -> UnitIntel:
    return UnitIntel(
        unit_id="unicorn",
        max_hp=2400,
        en_max=180,
        unit_attack=3200.0,
        unit_defense=2800.0,
        pilot_attack=1400.0,
        pilot_defense=1100.0,
        reaction=900.0,
        mobility=1300.0,
        move_range=5,
        weapons=(BEAM, MAP_GUN),
        skills=(REFILL,),
        chance_steps_max=1,
        support_attack_charges_max=2,
        support_defend_charges_max=1,
        has_shield=True,
        attack_shield=True,
        interception_reduction=0.15,
        pilot_shooting=583.0,
        pilot_melee=700.0,
        pilot_awakening=690.0,
        unit_lv=51,
        pilot_lv=22,
        pilot_sp=15,
    )


def test_learning_a_panel_records_it_and_marks_the_unit_known():
    intel = Intelligence()

    intel.learn(unicorn(), Side.ROSTER)

    assert intel.known("unicorn")
    assert intel.roster["unicorn"].max_hp == 2400
    assert intel.stage == {}


def test_a_cached_prior_gives_data_without_ever_claiming_it_was_seen():
    """快取只當先驗、畫面才是權威：assume 給得出沙盤數值，但不算 known，
    所以規劃還是會排 Inspect 去確認。"""
    intel = Intelligence()

    intel.assume(UnitIntel(unit_id="zaku", max_hp=900), Side.STAGE)

    assert intel.record("zaku") is not None
    assert not intel.known("zaku")


def test_an_unrecorded_unit_has_neither_data_nor_a_sandbox_unit():
    intel = Intelligence()

    assert intel.record("ghost") is None
    assert not intel.known("ghost")
    assert intel.unit("ghost", Faction.ENEMY) is None


def test_the_store_assembles_a_sandbox_unit_at_full_strength():
    intel = Intelligence()
    intel.learn(unicorn(), Side.ROSTER)

    unit = intel.unit("unicorn", Faction.ALLY, pos=(4, 7), acted=True)

    assert unit is not None
    assert unit.faction is Faction.ALLY
    assert unit.pos == (4, 7)
    assert unit.acted
    assert (unit.hp, unit.max_hp) == (2400, 2400)
    assert (unit.en, unit.en_max) == (180, 180)
    assert unit.move_range == 5
    assert [weapon.name for weapon in unit.weapons] == ["ビームライフル", "メガ粒子砲"]
    assert unit.weapon("メガ粒子砲").map_weapon
    assert unit.ammo == {"メガ粒子砲": 2}
    assert [skill.kind for skill in unit.skills] == [ActionKind.SKILL_EN_REFILL]
    assert unit.chance_steps == unit.chance_steps_max == 1
    assert unit.support_attack_charges == 2
    assert unit.support_defend_charges == 1
    assert (unit.has_shield, unit.attack_shield) == (True, True)
    assert unit.interception_reduction == 0.15


def test_the_weapon_carries_its_badges_its_crit_and_its_level():
    """類別是集合（一把可以掛多枚徽章）；爆擊%沙盤還沒接，先存原值不換算。"""
    intel = Intelligence()
    intel.learn(unicorn(), Side.ROSTER)

    weapon = intel.record("unicorn").weapons[0]

    assert weapon.categories == ("shooting",)
    assert (weapon.crit_pct, weapon.level) == (10, 2)


def test_the_pilot_offence_column_is_chosen_by_the_weapon_category():
    """遊戲把駕駛員攻擊拆射擊／格鬥／覺醒，沙盤只有一欄——挑選在組裝時發生。"""
    record = unicorn()

    assert record.offence_for(WeaponIntel("射", 1.0, categories=("shooting",))) == 583.0
    assert record.offence_for(WeaponIntel("格", 1.0, categories=("melee",))) == 700.0
    assert record.offence_for(WeaponIntel("覺", 1.0, categories=("awakening",))) == 690.0


def test_a_multi_badge_weapon_takes_the_lowest_applicable_column():
    """低估我方傷害只會讓 KILL 判準更保守，這個方向的錯是安全的。"""
    record = unicorn()

    assert record.offence_for(WeaponIntel("兩用", 1.0, categories=("melee", "shooting"))) == 583.0


def test_a_weapon_with_no_badge_falls_back_to_the_already_picked_column():
    record = unicorn()

    assert record.offence_for(WeaponIntel("無徽", 1.0)) == record.pilot_attack


def test_the_caller_can_override_pilot_attack_per_weapon_at_assembly():
    intel = Intelligence()
    intel.learn(unicorn(), Side.ROSTER)

    unit = intel.unit("unicorn", Faction.ALLY, pilot_attack=700.0)

    assert unit.pilot_attack == 700.0


def test_the_pilot_and_unit_levels_ride_along():
    intel = Intelligence()
    intel.learn(unicorn(), Side.ROSTER)
    record = intel.record("unicorn")

    assert (record.unit_lv, record.pilot_lv, record.pilot_sp) == (51, 22, 15)


def test_battlefield_dynamics_are_the_callers_to_supply():
    intel = Intelligence()
    intel.learn(unicorn(), Side.ROSTER)

    unit = intel.unit("unicorn", Faction.ALLY, hp=310, en=0)

    assert (unit.hp, unit.max_hp) == (310, 2400)
    assert (unit.en, unit.en_max) == (0, 180)


def test_the_json_round_trip_keeps_every_field_of_both_sections():
    intel = Intelligence()
    intel.learn(unicorn(), Side.ROSTER)
    intel.learn(UnitIntel(unit_id="zaku", max_hp=900, weapons=(BEAM,)), Side.STAGE)

    restored = loads(intel.dumps())

    assert restored.roster == intel.roster
    assert restored.stage == intel.stage
    assert restored.record("unicorn").skills == (REFILL,)


def test_reloading_a_file_restores_priors_not_confirmations():
    intel = Intelligence()
    intel.learn(UnitIntel(unit_id="zaku", max_hp=900), Side.STAGE)

    restored = loads(intel.dumps())

    assert restored.record("zaku") == intel.record("zaku")
    assert not restored.known("zaku")


def test_the_perceiver_seam_folds_the_stores_known_into_the_observation():
    intel = Intelligence()
    intel.learn(UnitIntel(unit_id="a1"), Side.ROSTER)
    intel.assume(UnitIntel(unit_id="e1"), Side.STAGE)
    seen = frame(battle(allies=["a1"], enemies=["e1", "e2"], known=[]), hp="93%")
    perceiver = IntelPerceiver(ScriptedPerceiver([seen]), intel)

    observation = perceiver.look()

    assert observation.state.known == {"a1"}
    assert observation.state.enemies == {"e1", "e2"}
    assert observation.evidence == {"hp": "93%"}


def test_the_perceiver_seam_tracks_the_store_as_inspections_land():
    intel = Intelligence()
    seen = frame(battle(allies=["a1"], enemies=["e1"], known=[]))
    perceiver = IntelPerceiver(ScriptedPerceiver([seen]), intel)

    assert perceiver.look().state.known == frozenset()

    intel.learn(UnitIntel(unit_id="e1"), Side.STAGE)

    assert perceiver.look().state.known == {"e1"}


def test_a_screen_with_no_symbolic_reading_passes_straight_through():
    perceiver = IntelPerceiver(ScriptedPerceiver([Observation(screen="cutscene")]), Intelligence())

    assert perceiver.look().state is None
