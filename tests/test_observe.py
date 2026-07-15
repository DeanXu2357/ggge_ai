"""Tactical map -> BattleState, and the advisor-proposal wiring (M4b)."""

import numpy as np

from ggge_ai.battle import controller as controller_mod
from ggge_ai.battle import vision
from ggge_ai.battle.bridge import UnitSpec
from ggge_ai.battle.controller import ManualBattleController
from ggge_ai.battle.ledger import BattleLedger
from ggge_ai.battle.observe import build_battle_state
from ggge_ai.battle.sim import SimWeapon
from ggge_ai.battle.state import Faction
from ggge_ai.battle.tacmap import TacticalMap
from ggge_ai.battle.vision import WeaponSelectForecast


def _tacmap():
    t = TacticalMap()
    t.allies.append((0.0, 0.0))
    t.allies.append((95.0, 0.0))
    t.enemies.append((400.0, 0.0))
    t.enemies.append((800.0, 300.0))
    t.third_party.append((100.0, 500.0))
    return t


def test_build_battle_state_assigns_factions_and_positions():
    battle = build_battle_state(_tacmap(), turn=3)
    assert battle.turn == 3
    assert len(battle.allies()) == 2
    assert len(battle.enemies()) == 2
    assert len(battle.by_faction(Faction.THIRD_PARTY)) == 1
    assert battle.enemies()[0].unit_id == "enemy_1"


def test_enemy_near_intel_tap_adopts_the_signature():
    sig = "a" * 16
    spec = UnitSpec(max_hp=51349)
    battle = build_battle_state(
        _tacmap(),
        specs_by_id={sig: spec},
        id_positions={sig: (420.0, 30.0)},
    )
    matched = battle.unit(sig)
    assert matched is not None
    assert matched.faction is Faction.ENEMY
    assert matched.max_hp == 51349
    other = battle.enemies()[1]
    assert other.unit_id == "enemy_2"


def test_far_signature_is_not_adopted():
    sig = "a" * 16
    battle = build_battle_state(_tacmap(), id_positions={sig: (2000.0, 2000.0)})
    assert battle.unit(sig) is None


def test_hub_poisoned_drops_unconfirmed_enemies():
    sig = "a" * 16
    notes: list[str] = []
    battle = build_battle_state(
        _tacmap(),
        id_positions={sig: (420.0, 30.0)},
        hub_poisoned=True,
        notes=notes,
    )
    assert [u.unit_id for u in battle.enemies()] == [sig]
    assert len(notes) == 1
    assert "dropped" in notes[0]


def test_hub_poisoned_without_sigs_yields_no_enemies():
    battle = build_battle_state(_tacmap(), hub_poisoned=True)
    assert battle.enemies() == []
    assert len(battle.allies()) == 2


def test_poisoned_red_arc_near_tracked_ally_rejoins_allies():
    ally_sig = "b" * 16
    spec = UnitSpec(max_hp=48000)
    notes: list[str] = []
    battle = build_battle_state(
        _tacmap(),
        specs_by_id={ally_sig: spec},
        ally_id_positions={ally_sig: (420.0, 30.0)},
        hub_poisoned=True,
        notes=notes,
    )
    recovered = battle.unit(ally_sig)
    assert recovered is not None
    assert recovered.faction is Faction.ALLY
    assert recovered.world_pos == (400.0, 0.0)
    assert recovered.max_hp == 48000
    assert battle.enemies() == []
    assert len(battle.allies()) == 3
    assert any("resolved as un-acted ally" in n for n in notes)
    assert any("dropped" in n for n in notes)


def test_ally_sig_taken_by_blue_arc_is_not_reused_for_recovery():
    ally_sig = "b" * 16
    t = TacticalMap()
    t.allies.append((400.0, 100.0))
    t.enemies.append((400.0, 0.0))
    notes: list[str] = []
    battle = build_battle_state(
        t,
        ally_id_positions={ally_sig: (400.0, 50.0)},
        hub_poisoned=True,
        notes=notes,
    )
    assert battle.enemies() == []
    assert [u.unit_id for u in battle.allies()] == [ally_sig]
    assert any("dropped" in n for n in notes)


def test_enemy_sig_wins_over_ally_recovery():
    enemy_sig = "a" * 16
    ally_sig = "b" * 16
    battle = build_battle_state(
        _tacmap(),
        id_positions={enemy_sig: (420.0, 30.0)},
        ally_id_positions={ally_sig: (420.0, 30.0)},
        hub_poisoned=True,
    )
    matched = battle.unit(enemy_sig)
    assert matched is not None
    assert matched.faction is Faction.ENEMY
    assert battle.unit(ally_sig) is None


def test_clean_scan_keeps_red_arcs_as_enemies():
    ally_sig = "b" * 16
    battle = build_battle_state(
        _tacmap(),
        ally_id_positions={ally_sig: (420.0, 30.0)},
        hub_poisoned=False,
    )
    assert battle.unit(ally_sig) is None
    assert len(battle.enemies()) == 2
    assert len(battle.allies()) == 2


class _Perception:
    def capture(self):
        return np.zeros((1080, 2340, 3), np.uint8)

    def probe(self, ids):
        return {}


class _Actuator:
    def tap(self, x, y):
        pass

    def swipe(self, *args):
        pass


def _armed_controller():
    c = ManualBattleController(
        perception=_Perception(),
        actuator=_Actuator(),
        ledger=BattleLedger(),
        advisor_enabled=True,
        advisor_time_budget_s=0.2,
    )
    sig = "a" * 16
    uid = f"sig:{sig}"
    c.tacmap.allies.append((0.0, 0.0))
    c.tacmap.enemies.append((400.0, 0.0))
    c.specs_by_id[uid] = UnitSpec(
        max_hp=8000,
        en_max=300,
        unit_attack=3000.0,
        unit_defense=1000.0,
        pilot_defense=100.0,
        reaction=100.0,
        mobility=1000.0,
        move_range=5,
        weapons=(SimWeapon(name="weapon_1_shooting", power=3000.0, range_max=5, en_cost=10),),
    )
    c._id_positions[uid] = (400.0, 0.0)
    return c, uid


def test_build_board_drops_unconfirmed_hub_enemies():
    c, sig = _armed_controller()
    c.tacmap.enemies.append((900.0, 500.0))

    battle, notes = c._build_board()

    assert [u.unit_id for u in battle.enemies()] == [sig]
    assert any("dropped" in n for n in notes)


def test_build_board_notes_missing_allies_against_card_count():
    c, _ = _armed_controller()
    c._card_count = 5

    battle, notes = c._build_board()

    assert len(battle.allies()) == 1
    assert any("missing allies" in n for n in notes)


def test_build_board_stays_quiet_when_cards_do_not_exceed_allies():
    c, _ = _armed_controller()
    c._card_count = 1

    _, notes = c._build_board()

    assert not any("missing allies" in n for n in notes)


def test_refresh_sig_positions_quiet_update_once_per_turn(monkeypatch):
    c, uid = _armed_controller()
    c.tracker.on_sig_position(uid[len("sig:"):], (400.0, 0.0))
    monkeypatch.setattr(vision, "find_enemy_units", lambda f, region=None: [(410, 10)])

    c._refresh_sig_positions(c.perception.capture())

    assert c._id_positions[uid] == (410.0, 10.0)
    assert c.tracker.beliefs[uid].world_pos == (410.0, 10.0)
    summaries = [e for e in c.ledger.events if e["kind"] == "sig_refresh_summary"]
    assert len(summaries) == 1
    assert summaries[0]["quiet"] == 1 and summaries[0]["taps"] == 0

    c._refresh_sig_positions(c.perception.capture())
    assert len([e for e in c.ledger.events if e["kind"] == "sig_refresh_summary"]) == 1


def test_consult_advisor_logs_a_proposal_once_per_turn():
    c, sig = _armed_controller()
    c._consult_advisor()
    proposals = [e for e in c.ledger.events if e["kind"] == "decision"]
    assert len(proposals) == 1
    assert proposals[0]["action"] == "proposal"
    assert c._proposal is not None

    c._consult_advisor()
    assert len([e for e in c.ledger.events if e["kind"] == "decision"]) == 1


def test_proposal_target_mismatch_is_flagged(monkeypatch):
    c, sig = _armed_controller()
    c._consult_advisor()
    assert c._proposal is not None
    c._proposal.target_id = sig

    other_sig = "b" * 16
    forecast = WeaponSelectForecast(
        target_name_sig=other_sig,
        target_hp=8000,
        target_en=300,
        predicted_damage=9000,
        hit_pct=None,
        our_name_sig="c" * 16,
        our_hp=50000,
        our_en=400,
    )
    monkeypatch.setattr(vision, "read_weapon_select_forecast", lambda f: forecast)
    monkeypatch.setattr(vision, "read_kill_counter", lambda f: (0, 14))
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    c._dispatched_mode = "label_weapon_select"

    c._register_attack_decision(c.perception.capture(), slot=1)

    mismatches = [
        e
        for e in c.ledger.events
        if e["kind"] == "sim_diverge" and e.get("divergence") == "proposal_target"
    ]
    assert len(mismatches) == 1
    assert mismatches[0]["proposal_target"] == sig
    assert mismatches[0]["actual_target"] == f"sig:{other_sig}"


def test_matching_target_is_silent(monkeypatch):
    c, sig = _armed_controller()
    c._consult_advisor()
    c._proposal.target_id = sig
    forecast = WeaponSelectForecast(
        target_name_sig=sig[len("sig:"):],
        target_hp=8000,
        target_en=300,
        predicted_damage=9000,
        hit_pct=None,
        our_name_sig="c" * 16,
        our_hp=50000,
        our_en=400,
    )
    monkeypatch.setattr(vision, "read_weapon_select_forecast", lambda f: forecast)
    monkeypatch.setattr(vision, "read_kill_counter", lambda f: (0, 14))
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    c._dispatched_mode = "label_weapon_select"

    c._register_attack_decision(c.perception.capture(), slot=1)

    assert not [
        e
        for e in c.ledger.events
        if e["kind"] == "sim_diverge" and e.get("divergence") == "proposal_target"
    ]
