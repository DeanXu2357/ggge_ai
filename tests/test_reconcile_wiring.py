"""Controller wiring of the reconciliation chain: decision -> forecast ->
battle-prep refinement -> 破壞數 verdict, as ledger evidence."""

import numpy as np

from ggge_ai.battle import controller as controller_mod
from ggge_ai.battle import vision
from ggge_ai.battle.controller import ManualBattleController
from ggge_ai.battle.ledger import BattleLedger
from ggge_ai.battle.vision import BattlePrepForecast, WeaponSelectForecast


class _Perception:
    def capture(self):
        return np.zeros((1080, 2340, 3), np.uint8)

    def probe(self, ids):
        return {}


class _Actuator:
    def __init__(self):
        self.taps = []

    def tap(self, x, y):
        self.taps.append((x, y))

    def swipe(self, *args):
        pass


def _controller():
    return ManualBattleController(
        perception=_Perception(), actuator=_Actuator(), ledger=BattleLedger()
    )


def _kinds(c):
    return [e["kind"] for e in c.ledger.events]


def _event(c, kind):
    return next(e for e in c.ledger.events if e["kind"] == kind)


FORECAST = WeaponSelectForecast(
    target_name_sig="t" * 16,
    target_hp=8000,
    target_en=300,
    predicted_damage=9000,
    hit_pct=None,
    our_name_sig="a" * 16,
    our_hp=50000,
    our_en=400,
)
PREP = BattlePrepForecast(
    is_reaction=False,
    attack_value=9000,
    defense_value=0,
    hit_pct=62,
    attacker_name_sig="a" * 16,
    attacker_hp=50000,
    attacker_en=400,
    defender_name_sig="t" * 16,
    defender_hp=8000,
    defender_en=300,
    defender_hp_delta=8000,
    support_defense=None,
)


def _wire(monkeypatch, c, counters):
    """Stub the vision readers; `counters` is consumed by read_kill_counter
    one value per call."""
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(vision, "read_weapon_select_forecast", lambda f: FORECAST)
    monkeypatch.setattr(vision, "read_battle_prep_forecast", lambda f: PREP)
    feed = iter(counters)
    monkeypatch.setattr(vision, "read_kill_counter", lambda f: next(feed))


def test_full_chain_confirmed_kill(monkeypatch):
    c = _controller()
    _wire(monkeypatch, c, [(3, 14), (4, 14)])
    c._dispatched_mode = "label_weapon_select"

    frame = c.perception.capture()
    c._register_attack_decision(frame, slot=1)
    c._attack(slot=1)
    c._check_expectation("label_battle_prep")
    c._dispatched_mode = "label_battle_prep"
    c._on_battle_prep()
    assert c._pending is not None and c._pending.armed

    c._judge_pending("label_our_turn")
    assert c._pending is None

    kinds = _kinds(c)
    for expected in (
        "forecast_weapon_select",
        "sim_skip",
        "decision",
        "attack",
        "forecast_battle_prep",
        "kill_check",
    ):
        assert expected in kinds, f"missing {expected} in {kinds}"
    decision = _event(c, "decision")
    assert decision["quality"] == "none"
    assert decision["source"] == "heuristic_v1"
    check = _event(c, "kill_check")
    assert check["result"] == "confirmed"
    assert check["counter_before"] == [3, 14]
    assert check["counter_after"] == [4, 14]
    assert check["hit_pct"] == 62
    attack = _event(c, "attack")
    assert attack["target"] == "sig:" + "t" * 16
    assert attack["target_sig_seen"] == "t" * 16
    assert attack["predicted_damage_game"] == 9000
    assert attack["expect_kill"] is True


def test_expected_kill_missed_at_partial_hit_is_rng_branch(monkeypatch):
    c = _controller()
    _wire(monkeypatch, c, [(3, 14), (3, 14)])
    c._dispatched_mode = "label_weapon_select"

    c._register_attack_decision(c.perception.capture(), slot=1)
    c._attack(slot=1)
    c._dispatched_mode = "label_battle_prep"
    c._on_battle_prep()
    c._judge_pending("label_our_turn")

    assert _event(c, "kill_check")["result"] == "rng_branch"
    assert "rng_branch" in _kinds(c)


def test_pending_not_judged_before_engagement(monkeypatch):
    c = _controller()
    _wire(monkeypatch, c, [(3, 14)])
    c._dispatched_mode = "label_weapon_select"

    c._register_attack_decision(c.perception.capture(), slot=1)
    c._attack(slot=1)
    c._judge_pending("label_weapon_select")

    assert c._pending is not None
    assert "kill_check" not in _kinds(c)


def test_standby_drops_unarmed_pending(monkeypatch):
    c = _controller()
    _wire(monkeypatch, c, [(3, 14)])
    monkeypatch.setattr(vision, "unit_cards_present", lambda f: False)
    c._dispatched_mode = "label_weapon_select"

    c._register_attack_decision(c.perception.capture(), slot=1)
    c._standby("out_of_range")

    assert c._pending is None


def test_unreadable_counter_burns_budget_then_unverified(monkeypatch):
    c = _controller()
    _wire(monkeypatch, c, [(3, 14)] + [None] * 20)
    c._dispatched_mode = "label_weapon_select"

    c._register_attack_decision(c.perception.capture(), slot=1)
    c._dispatched_mode = "label_battle_prep"
    c._on_battle_prep()
    for _ in range(controller_mod.reconcile.KILL_CHECK_BUDGET):
        c._judge_pending("label_our_turn")

    assert c._pending is None
    assert _event(c, "kill_check")["result"] == "unverified_counter_unreadable"


def test_tracker_follows_the_full_chain(monkeypatch):
    c = _controller()
    _wire(monkeypatch, c, [(3, 14), (4, 14)])
    c._dispatched_mode = "label_weapon_select"

    c._register_attack_decision(c.perception.capture(), slot=1)
    assert c.tracker.beliefs["sig:" + "t" * 16].hp == 8000
    assert c.tracker.beliefs["sig:" + "a" * 16].hp == 50000

    c._attack(slot=1)
    c._dispatched_mode = "label_battle_prep"
    c._on_battle_prep()
    c._judge_pending("label_our_turn")

    assert c.tracker.beliefs["sig:" + "t" * 16].alive is False
    assert ("sig:" + "t" * 16) not in c.tracker.id_positions()


def test_tracker_keeps_hp_on_a_missed_kill(monkeypatch):
    c = _controller()
    _wire(monkeypatch, c, [(3, 14), (3, 14)])
    c._dispatched_mode = "label_weapon_select"

    c._register_attack_decision(c.perception.capture(), slot=1)
    c._attack(slot=1)
    c._dispatched_mode = "label_battle_prep"
    c._on_battle_prep()
    c._judge_pending("label_our_turn")

    belief = c.tracker.beliefs["sig:" + "t" * 16]
    assert belief.alive is True
    assert belief.hp == 8000


def test_reaction_prep_records_without_touching_pending(monkeypatch):
    c = _controller()
    reaction = BattlePrepForecast(
        is_reaction=True,
        attack_value=2626,
        defense_value=0,
        hit_pct=62,
        attacker_name_sig="e" * 16,
        attacker_hp=15721,
        attacker_en=402,
        defender_name_sig="d" * 16,
        defender_hp=9045,
        defender_en=241,
        defender_hp_delta=2626,
        support_defense=None,
    )
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(vision, "read_battle_prep_forecast", lambda f: reaction)
    c._dispatched_mode = "label_battle_prep"

    c._on_battle_prep()

    assert c._pending is None
    prep = _event(c, "forecast_battle_prep")
    assert prep["is_reaction"] is True
    assert prep["attack_value"] == 2626
    assert "label_battle_prep" in c._expectation.targets
