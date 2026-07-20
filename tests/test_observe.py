"""Factionless pool -> BattleState (the evidence ladder), and the
advisor-proposal wiring (M4b). Arc colors never decide faction: a point
enters the board only when a resolver identity, a tracked ally sig or a
census ally position claims it; everything else drops with a note."""

import numpy as np

from ggge_ai.battle import controller as controller_mod
from ggge_ai.battle import vision
from ggge_ai.content.kit import UnitSpec
from ggge_ai.battle.controller import ManualBattleController
from ggge_ai.battle.ledger import BattleLedger
from ggge_ai.battle.observe import build_battle_state
from ggge_ai.sim import SimWeapon
from ggge_ai.battle.state import Faction
from ggge_ai.battle.vision import WeaponSelectForecast


def _units():
    return [(0.0, 0.0), (95.0, 0.0), (400.0, 0.0), (800.0, 300.0), (100.0, 500.0)]


def test_evidence_ladder_assigns_factions_and_positions():
    notes: list[str] = []
    battle = build_battle_state(
        _units(),
        id_positions={"e01": (420.0, 30.0), "t01": (120.0, 520.0)},
        faction_by_id={"e01": Faction.ENEMY, "t01": Faction.THIRD_PARTY},
        ally_points=[(0.0, 0.0), (95.0, 0.0)],
        turn=3,
        notes=notes,
    )
    assert battle.turn == 3
    assert [u.unit_id for u in battle.enemies()] == ["e01"]
    assert [u.unit_id for u in battle.by_faction(Faction.THIRD_PARTY)] == ["t01"]
    assert len(battle.allies()) == 2
    assert battle.enemies()[0].world_pos == (400.0, 0.0)
    assert len(notes) == 1 and "dropped" in notes[0]


def test_identity_carries_the_spec():
    battle = build_battle_state(
        [(400.0, 0.0)],
        specs_by_id={"e01": UnitSpec(max_hp=51349)},
        id_positions={"e01": (420.0, 30.0)},
    )
    unit = battle.unit("e01")
    assert unit is not None
    assert unit.faction is Faction.ENEMY
    assert unit.max_hp == 51349


def test_far_identity_does_not_claim():
    notes: list[str] = []
    battle = build_battle_state(
        [(400.0, 0.0)],
        id_positions={"e01": (2000.0, 2000.0)},
        notes=notes,
    )
    assert battle.unit("e01") is None
    assert battle.enemies() == []
    assert len(notes) == 1 and "dropped" in notes[0]


def test_tracked_ally_sig_claims_with_spec():
    ally_sig = "b" * 16
    battle = build_battle_state(
        [(400.0, 0.0)],
        specs_by_id={ally_sig: UnitSpec(max_hp=48000)},
        ally_id_positions={ally_sig: (420.0, 30.0)},
    )
    unit = battle.unit(ally_sig)
    assert unit is not None
    assert unit.faction is Faction.ALLY
    assert unit.world_pos == (400.0, 0.0)
    assert unit.max_hp == 48000


def test_enemy_identity_wins_over_ally_sig():
    enemy_sig = "a" * 16
    ally_sig = "b" * 16
    battle = build_battle_state(
        [(400.0, 0.0)],
        id_positions={enemy_sig: (420.0, 30.0)},
        ally_id_positions={ally_sig: (420.0, 30.0)},
    )
    unit = battle.unit(enemy_sig)
    assert unit is not None
    assert unit.faction is Faction.ENEMY
    assert battle.unit(ally_sig) is None


def test_census_point_claims_an_anonymous_ally():
    battle = build_battle_state(
        [(400.0, 0.0)],
        ally_points=[(410.0, 20.0)],
    )
    assert len(battle.allies()) == 1
    unit = battle.allies()[0]
    assert unit.unit_id == "ally_1"
    assert unit.world_pos == (400.0, 0.0)


def test_unclaimed_board_drops_everything_with_notes():
    notes: list[str] = []
    battle = build_battle_state(_units(), notes=notes)
    assert battle.units == []
    assert len(notes) == len(_units())


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
    c.tacmap.units.append((0.0, 0.0))
    c.tacmap.units.append((400.0, 0.0))
    c._ally_points.append((0.0, 0.0))
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


def test_build_board_drops_unclaimed_points():
    c, sig = _armed_controller()
    c.tacmap.units.append((900.0, 500.0))

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
    monkeypatch.setattr(vision, "find_ally_units", lambda f, region=None: [])
    monkeypatch.setattr(vision, "find_third_party_units", lambda f, region=None: [])

    c._refresh_sig_positions(c.perception.capture())

    assert c._id_positions[uid] == (410.0, 10.0)
    assert c.tracker.beliefs[uid].world_pos == (410.0, 10.0)
    summaries = [e for e in c.ledger.events if e["kind"] == "sig_refresh_summary"]
    assert len(summaries) == 1
    assert summaries[0]["quiet"] == 1 and summaries[0]["taps"] == 0

    c._refresh_sig_positions(c.perception.capture())
    assert len([e for e in c.ledger.events if e["kind"] == "sig_refresh_summary"]) == 1


def test_refresh_skips_candidates_hugging_known_allies(monkeypatch):
    c, uid = _armed_controller()
    c.tracker.on_sig_position(uid[len("sig:"):], (400.0, 0.0))
    monkeypatch.setattr(
        vision, "find_enemy_units", lambda f, region=None: [(30, 20)]
    )
    monkeypatch.setattr(vision, "find_ally_units", lambda f, region=None: [])
    monkeypatch.setattr(vision, "find_third_party_units", lambda f, region=None: [])

    c._refresh_sig_positions(c.perception.capture())

    # the only candidate hugs the census ally at (0,0): nothing to refresh
    assert c._id_positions[uid] == (400.0, 0.0)
    assert not [e for e in c.ledger.events if e["kind"] == "sig_refresh_summary"]


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
