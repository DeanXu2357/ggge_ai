"""HP audit layer (silent-events batch B, issue #27).

Three seams under test: the pure divergence check, the tracker `_set_hp`
mount (which read points fire and which stay un-audited), and the controller
wiring that records `unattributed_damage` on an in-memory ledger. Pure
offline -- no adb, no images."""

import numpy as np

from ggge_ai.battle.audit import (
    AUDIT_TOL_ABS,
    AUDIT_TOL_RATIO,
    HpDivergence,
    check_hp_divergence,
)
from ggge_ai.battle.controller import ManualBattleController
from ggge_ai.battle.ledger import BattleLedger
from ggge_ai.battle.reconcile import PendingOutcome, SimExpectation
from ggge_ai.battle.scout_intel import StageIntel
from ggge_ai.battle.state import Faction
from ggge_ai.battle.tracker import BoardTracker, UnitBelief
from ggge_ai.battle.vision import BattlePrepForecast, EnemySummary, WeaponSelectForecast

ENEMY_SIG = "e" * 16
ALLY_SIG = "a" * 16
ENEMY_UID = f"sig:{ENEMY_SIG}"
ALLY_UID = f"sig:{ALLY_SIG}"


def _belief(**overrides) -> UnitBelief:
    base = dict(
        sig=ENEMY_SIG, faction=Faction.ENEMY, uid=ENEMY_UID, hp=8000,
        world_pos=(400.0, 20.0), hp_turn=2, source="forecast",
    )
    base.update(overrides)
    return UnitBelief(**base)


def _forecast(**overrides) -> WeaponSelectForecast:
    base = dict(
        target_name_sig=ENEMY_SIG, target_hp=8000, target_en=120,
        predicted_damage=5000, hit_pct=None,
        our_name_sig=ALLY_SIG, our_hp=30000, our_en=250,
    )
    base.update(overrides)
    return WeaponSelectForecast(**base)


def _prep(**overrides) -> BattlePrepForecast:
    base = dict(
        is_reaction=False, attack_value=5000, defense_value=1000, hit_pct=100,
        attacker_name_sig=ENEMY_SIG, attacker_hp=8000, attacker_en=120,
        defender_name_sig=ALLY_SIG, defender_hp=30000, defender_en=240,
        defender_hp_delta=None, support_defense=None,
    )
    base.update(overrides)
    return BattlePrepForecast(**base)


def _pending(*, expect_kill=None, quality="grounded", game_damage=5000,
             target_hp_game=8000, game_expect_kill=None, hit_pct=None) -> PendingOutcome:
    expectation = SimExpectation(
        attacker_id=ALLY_UID, target_id=ENEMY_UID, weapon_slot=1,
        target_sig_seen=ENEMY_SIG,
        expected_damage=float(game_damage), target_hp_believed=target_hp_game,
        expect_kill=expect_kill, hit_probability=0.9,
        source="formulas", quality=quality,
    )
    return PendingOutcome(
        expectation=expectation, game_damage=game_damage,
        target_hp_game=target_hp_game, game_expect_kill=game_expect_kill,
        counter_before=(0, 14), hit_pct=hit_pct,
    )



def test_first_read_has_no_prior_to_reconcile():
    assert check_hp_divergence(
        _belief(hp=None), 8000, 3, "forecast", tol_abs=0, tol_ratio=0.0
    ) is None


def test_equal_read_is_within_zero_tolerance():
    assert check_hp_divergence(
        _belief(hp=8000), 8000, 3, "forecast", tol_abs=0, tol_ratio=0.0
    ) is None


def test_negative_delta_carries_every_field():
    div = check_hp_divergence(
        _belief(hp=8000, hp_turn=2, source="prep", world_pos=(400.0, 20.0)),
        5000, 4, "forecast", tol_abs=0, tol_ratio=0.0,
    )
    assert div == HpDivergence(
        uid=ENEMY_UID, expected_hp=8000, observed_hp=5000, delta=-3000, turn=4,
        read_source="forecast", prior_source="prep", prior_hp_turn=2,
        world_pos=(400.0, 20.0),
    )


def test_positive_delta_is_unattributed_recovery():
    div = check_hp_divergence(
        _belief(hp=5000), 8000, 4, "intel", tol_abs=0, tol_ratio=0.0
    )
    assert div is not None
    assert div.delta == 3000


def test_tol_abs_gates_small_residuals():
    within = check_hp_divergence(
        _belief(hp=8000), 7950, 4, "forecast", tol_abs=100, tol_ratio=0.0
    )
    beyond = check_hp_divergence(
        _belief(hp=8000), 7800, 4, "forecast", tol_abs=100, tol_ratio=0.0
    )
    assert within is None
    assert beyond is not None and beyond.delta == -200


def test_tol_ratio_scales_with_prior_hp():
    # 10% of 10000 = 1000 threshold
    within = check_hp_divergence(
        _belief(hp=10000), 9500, 4, "forecast", tol_abs=0, tol_ratio=0.1
    )
    beyond = check_hp_divergence(
        _belief(hp=10000), 8500, 4, "forecast", tol_abs=0, tol_ratio=0.1
    )
    assert within is None
    assert beyond is not None and beyond.delta == -1500


def test_default_constants_record_any_nonzero_residual():
    div = check_hp_divergence(
        _belief(hp=8000), 7999, 4, "forecast",
        tol_abs=AUDIT_TOL_ABS, tol_ratio=AUDIT_TOL_RATIO,
    )
    assert div is not None and div.delta == -1



def _sink() -> tuple[BoardTracker, list[HpDivergence]]:
    seen: list[HpDivergence] = []
    t = BoardTracker(on_hp_divergence=seen.append)
    return t, seen


def test_intel_path_fires_on_second_read():
    t, seen = _sink()
    intel = StageIntel()
    intel.summaries[ENEMY_SIG] = EnemySummary(name_sig=ENEMY_SIG, hp=8000, en=300)
    t.on_intel(intel)  # first read seeds; prior None -> no residual
    intel.summaries[ENEMY_SIG] = EnemySummary(name_sig=ENEMY_SIG, hp=5000, en=300)
    t.on_intel(intel)
    assert [d.delta for d in seen] == [-3000]
    assert seen[0].read_source == "intel"
    assert seen[0].uid == ENEMY_UID


def test_weapon_select_path_fires():
    t, seen = _sink()
    t.on_weapon_select(_forecast(target_hp=8000))
    t.on_weapon_select(_forecast(target_hp=6000))
    assert [d.delta for d in seen] == [-2000]
    assert seen[0].read_source == "forecast"


def test_battle_prep_path_fires():
    t, seen = _sink()
    t.on_battle_prep(_prep(attacker_hp=8000))
    t.on_battle_prep(_prep(attacker_hp=7000))
    assert [d.delta for d in seen] == [-1000]
    assert seen[0].read_source == "prep"


def test_kill_path_fires_on_last_known_to_zero_gap():
    t, seen = _sink()
    t.on_weapon_select(_forecast(target_hp=8000), target_world=(400.0, 20.0))
    t.on_outcome(_pending(expect_kill=True), "confirmed", delta=1)
    assert [d.delta for d in seen] == [-8000]
    assert seen[0].observed_hp == 0
    assert seen[0].read_source == "outcome"


def test_estimate_subtraction_stays_un_audited():
    t, seen = _sink()
    t.on_weapon_select(_forecast(target_hp=8000))
    t.on_outcome(_pending(expect_kill=False, game_damage=5000, hit_pct=100),
                 "confirmed", delta=0)
    assert t.beliefs[ENEMY_UID].hp == 3000
    assert seen == []


def test_definition_direct_write_stays_un_audited():
    # definition seeding writes belief.hp directly (controller path), never
    # through _set_hp, so a later read reconciles against it but the seeding
    # itself raises no residual
    t, seen = _sink()
    t.beliefs[ENEMY_UID] = UnitBelief(
        sig=ENEMY_SIG, faction=Faction.ENEMY, uid=ENEMY_UID, hp=51349,
        source="definition",
    )
    assert seen == []
    t.on_weapon_select(_forecast(target_hp=51349))
    assert seen == []


def test_callback_none_is_safe():
    t = BoardTracker()  # on_hp_divergence defaults None
    t.on_weapon_select(_forecast(target_hp=8000))
    t.on_weapon_select(_forecast(target_hp=1000))
    assert t.beliefs[ENEMY_UID].hp == 1000



class _Perception:
    def capture(self):
        return np.zeros((1080, 2340, 3), np.uint8)


class _Actuator:
    def tap(self, x, y):
        pass


def _controller(ledger: BattleLedger | None) -> ManualBattleController:
    return ManualBattleController(
        perception=_Perception(), actuator=_Actuator(), ledger=ledger
    )


def _unattributed(c: ManualBattleController) -> list[dict]:
    return [e for e in c.ledger.events if e["kind"] == "unattributed_damage"]


def test_wiring_records_event_shape_and_turn():
    c = _controller(BattleLedger())  # stream_path=None, in-memory
    c.tracker.on_turn(2)
    c.tracker.on_weapon_select(_forecast(target_hp=8000))  # seed, no residual
    c.tracker.on_weapon_select(_forecast(target_hp=5000))  # residual on enemy
    events = _unattributed(c)
    assert len(events) == 1
    ev = events[0]
    assert ev["uid"] == ENEMY_UID
    assert ev["expected_hp"] == 8000
    assert ev["observed_hp"] == 5000
    assert ev["delta"] == -3000
    assert ev["turn"] == 2
    assert ev["read_source"] == "forecast"
    assert ev["prior_source"] == "forecast"
    assert ev["prior_hp_turn"] == 2
    assert "frame" not in ev


def test_wiring_records_kill_reality_gap():
    c = _controller(BattleLedger())
    c.tracker.on_turn(3)
    c.tracker.on_weapon_select(_forecast(target_hp=8000), target_world=(400.0, 20.0))
    c.tracker.on_outcome(_pending(expect_kill=True), "confirmed", delta=1)
    events = _unattributed(c)
    assert len(events) == 1
    assert events[0]["observed_hp"] == 0
    assert events[0]["delta"] == -8000
    assert events[0]["turn"] == 3


def test_ledgerless_config_does_not_wire_the_audit():
    c = _controller(None)
    assert c.tracker.on_hp_divergence is None
    c.tracker.on_weapon_select(_forecast(target_hp=8000))
    c.tracker.on_weapon_select(_forecast(target_hp=2000))  # must not crash
    assert c.tracker.beliefs[ENEMY_UID].hp == 2000
