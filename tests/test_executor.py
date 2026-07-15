"""Advice execution: pure primitives, and the controller pilot flow
(fail-fast on alignment failures, greedy demotion on no-opinion)."""

import numpy as np
import pytest

from ggge_ai.battle import advisor as advisor_mod
from ggge_ai.battle import controller as controller_mod
from ggge_ai.battle import executor, vision
from ggge_ai.battle.advisor import Advice
from ggge_ai.battle.bridge import UnitSpec
from ggge_ai.battle.controller import ManualBattleController, PilotAbort
from ggge_ai.battle.identity import IdentityResolver
from ggge_ai.battle.ledger import BattleLedger
from ggge_ai.battle.sim import SimWeapon
from ggge_ai.battle.state import BattleState, Faction, UnitState
from ggge_ai.battle.tacmap import TacticalMap
from ggge_ai.battle.vision import WeaponSelectForecast

ENEMY_SIG = "e" * 16
OUR_SIG = "c" * 16
ENEMY_UID = f"sig:{ENEMY_SIG}"
_RESOLVER = IdentityResolver()


def _advice(**kw):
    base = dict(
        unit_id="ally_1", kind="attack", move_world=None, target_id=ENEMY_UID,
        weapon="rifle", value=100.0, pv_kinds=[], assumptions=[], stats=None,
    )
    base.update(kw)
    return Advice(**base)


def _spec(**kw):
    base = dict(weapons=(SimWeapon("rifle", power=3000, range_min=1, range_max=3),))
    base.update(kw)
    return UnitSpec(**base)


def _forecast(**kw):
    base = dict(
        target_name_sig=ENEMY_SIG, target_hp=8000, target_en=300,
        predicted_damage=9000, hit_pct=None,
        our_name_sig=OUR_SIG, our_hp=50000, our_en=400,
    )
    base.update(kw)
    return WeaponSelectForecast(**base)


def test_slot_for_maps_weapon_name_to_slot():
    spec = UnitSpec(weapons=(
        SimWeapon("vulcan", power=1000, range_min=1, range_max=1),
        SimWeapon("rifle", power=3000, range_min=1, range_max=3),
    ))
    assert executor.slot_for(_advice(weapon="rifle"), spec) == 2
    assert executor.slot_for(_advice(weapon="saber"), spec) is None
    assert executor.slot_for(_advice(), None) is None


def test_target_ok_requires_a_readable_matching_sig():
    assert executor.target_ok(_forecast(), _advice(), _RESOLVER)
    assert not executor.target_ok(_forecast(target_name_sig="0" * 16), _advice(), _RESOLVER)
    assert not executor.target_ok(_forecast(target_name_sig=None), _advice(), _RESOLVER)
    assert not executor.target_ok(None, _advice(), _RESOLVER)


def test_target_ok_tolerates_panel_sig_jitter():
    advice = _advice(target_id="sig:9115599951d15595")
    assert executor.target_ok(
        _forecast(target_name_sig="9119599551d155d5"), advice, _RESOLVER
    )


def test_verifiable_target_rejects_positional_ids():
    assert executor.verifiable_target(ENEMY_UID, _RESOLVER)
    assert not executor.verifiable_target("enemy_3", _RESOLVER)
    assert not executor.verifiable_target(None, _RESOLVER)


def test_pilot_positional_target_demotes_to_greedy(monkeypatch):
    advice = _advice(kind="attack", target_id="enemy_3")
    c = _pilot_controller(monkeypatch, advice, specs={"ally_1": _spec()})

    c._on_unit_move()

    fallbacks = [e for e in c.ledger.events if e["kind"] == "pilot_fallback"]
    assert len(fallbacks) == 1 and fallbacks[0]["reason"] == "unverifiable_target"
    assert controller_mod.WEAPON_SELECT_BTN in c.actuator.taps


def test_move_tap_snaps_to_the_nearest_cell():
    advice = _advice(kind="move", move_world=(300.0, 100.0))
    kind, point = executor.move_tap(advice, (100.0, 50.0), [(190, 55), (500, 400)])
    assert kind == "cell"
    assert point == (190, 55)


def test_move_tap_far_cells_are_an_alignment_failure():
    advice = _advice(kind="move", move_world=(300.0, 100.0))
    assert executor.move_tap(advice, (0.0, 0.0), [(900, 900)]) is None


def test_move_tap_without_cells_taps_the_raw_point():
    advice = _advice(kind="move", move_world=(300.0, 100.0))
    kind, point = executor.move_tap(advice, (100.0, 50.0), [])
    assert kind == "direct"
    assert point == (200, 50)


def test_resolve_ally_requires_a_unique_match():
    battle = BattleState()
    battle.add_unit(UnitState("ally_1", Faction.ALLY, world_pos=(0.0, 0.0)))
    battle.add_unit(UnitState("ally_2", Faction.ALLY, world_pos=(600.0, 0.0)))
    assert executor.resolve_ally(battle, (10.0, 10.0)) == "ally_1"
    assert executor.resolve_ally(battle, (300.0, 0.0)) is None
    crowded = BattleState()
    crowded.add_unit(UnitState("ally_1", Faction.ALLY, world_pos=(0.0, 0.0)))
    crowded.add_unit(UnitState("ally_2", Faction.ALLY, world_pos=(90.0, 0.0)))
    assert executor.resolve_ally(crowded, (40.0, 0.0)) is None


def test_identify_recovers_camera_from_the_constellation(monkeypatch):
    tacmap = TacticalMap()
    tacmap.allies.append((0.0, 0.0))
    tacmap.enemies.append((400.0, 0.0))
    monkeypatch.setattr(vision, "find_ally_units", lambda f, region=None: [(0, 0)])
    monkeypatch.setattr(vision, "find_enemy_units", lambda f, region=None: [(400, 0)])
    monkeypatch.setattr(vision, "find_third_party_units", lambda f, region=None: [])
    found = executor.identify(None, tacmap, (0, 0))
    assert found is not None
    unit_world, camera = found
    assert camera == (0.0, 0.0)
    assert unit_world == (0.0, 0.0)


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


def _pilot_controller(monkeypatch, advice, *, specs=None):
    c = ManualBattleController(
        perception=_Perception(),
        actuator=_Actuator(),
        ledger=BattleLedger(),
        pilot_enabled=True,
        pilot_time_budget_s=0.2,
    )
    c.tacmap.allies.append((0.0, 0.0))
    c.tacmap.enemies.append((400.0, 0.0))
    if specs:
        c.specs_by_id.update(specs)
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(vision, "find_move_cells", lambda f: [])
    monkeypatch.setattr(
        controller_mod.executor, "identify", lambda f, t, o: ((0.0, 0.0), (0.0, 0.0))
    )
    monkeypatch.setattr(advisor_mod, "advise", lambda *a, **k: advice)
    return c


def _kinds(c):
    return [e["kind"] for e in c.ledger.events]


def test_pilot_standby_advice_stands_by(monkeypatch):
    c = _pilot_controller(monkeypatch, _advice(kind="standby"))
    monkeypatch.setattr(vision, "unit_cards_present", lambda f: False)

    c._on_unit_move()

    assert controller_mod.STANDBY_BTN in c.actuator.taps
    kinds = _kinds(c)
    assert "pilot_plan" in kinds and "pilot_step" in kinds and "standby" in kinds


def test_pilot_attack_in_place_selects_slot_and_attacks(monkeypatch):
    advice = _advice(kind="attack", weapon="rifle", target_id=ENEMY_UID)
    c = _pilot_controller(monkeypatch, advice, specs={"ally_1": _spec()})

    c._on_unit_move()
    assert controller_mod.WEAPON_SELECT_BTN in c.actuator.taps
    assert c._action.plan is not None and c._action.plan.weapon_slot == 1

    monkeypatch.setattr(vision, "attack_enabled", lambda f: True)
    monkeypatch.setattr(vision, "read_weapon_select_forecast", lambda f: _forecast())
    monkeypatch.setattr(vision, "read_kill_counter", lambda f: (0, 14))
    c._dispatched_mode = "label_weapon_select"
    c._on_weapon_select()

    assert controller_mod.WEAPON_SLOTS[0] in c.actuator.taps
    assert controller_mod.ATTACK_BTN in c.actuator.taps
    steps = [e for e in c.ledger.events if e["kind"] == "pilot_step"]
    assert [s["step"] for s in steps] == ["open_weapon_select", "attack"]
    assert c.tracker.beliefs[f"sig:{OUR_SIG}"].world_pos == (0.0, 0.0)


def test_pilot_move_then_attack(monkeypatch):
    advice = _advice(kind="attack", move_world=(190.0, 0.0))
    c = _pilot_controller(monkeypatch, advice, specs={"ally_1": _spec()})
    monkeypatch.setattr(vision, "find_move_cells", lambda f: [(180, 10)])

    c._on_unit_move()
    assert (180, 10) in c.actuator.taps
    assert c._action.moved

    c._on_unit_move()
    assert controller_mod.WEAPON_SELECT_BTN in c.actuator.taps
    steps = [e["step"] for e in c.ledger.events if e["kind"] == "pilot_step"]
    assert steps == ["move", "open_weapon_select"]


def test_pilot_move_advice_ends_with_standby(monkeypatch):
    advice = _advice(kind="move", move_world=(190.0, 0.0), target_id=None, weapon=None)
    c = _pilot_controller(monkeypatch, advice)
    monkeypatch.setattr(vision, "find_move_cells", lambda f: [(185, 5)])
    monkeypatch.setattr(vision, "unit_cards_present", lambda f: False)

    c._on_unit_move()
    c._on_unit_move()

    assert controller_mod.STANDBY_BTN in c.actuator.taps
    steps = [e["step"] for e in c.ledger.events if e["kind"] == "pilot_step"]
    assert steps == ["move", "standby_after_move"]


def test_pilot_unreachable_move_aborts(monkeypatch):
    advice = _advice(kind="move", move_world=(190.0, 0.0))
    c = _pilot_controller(monkeypatch, advice)
    monkeypatch.setattr(vision, "find_move_cells", lambda f: [(900, 900)])

    with pytest.raises(PilotAbort):
        c._on_unit_move()
    aborts = [e for e in c.ledger.events if e["kind"] == "pilot_abort"]
    assert len(aborts) == 1 and aborts[0]["reason"] == "move_unreachable"


def test_pilot_anchor_failure_aborts(monkeypatch):
    c = _pilot_controller(monkeypatch, _advice())
    monkeypatch.setattr(controller_mod.executor, "identify", lambda f, t, o: None)

    with pytest.raises(PilotAbort):
        c._on_unit_move()
    assert [e["reason"] for e in c.ledger.events if e["kind"] == "pilot_abort"] == [
        "anchor_failed"
    ]


def test_pilot_no_advice_demotes_to_greedy(monkeypatch):
    # a non-empty board with no opinion is a greedy demotion, not an abort
    c = _pilot_controller(monkeypatch, None)
    c._id_positions[ENEMY_UID] = (400.0, 0.0)
    monkeypatch.setattr(vision, "unit_cards_present", lambda f: False)

    c._on_unit_move()

    fallbacks = [e for e in c.ledger.events if e["kind"] == "pilot_fallback"]
    assert len(fallbacks) == 1 and fallbacks[0]["reason"] == "no_advice"
    assert controller_mod.WEAPON_SELECT_BTN in c.actuator.taps


def test_pilot_empty_board_resyncs_once_then_aborts(monkeypatch):
    c = _pilot_controller(monkeypatch, None)
    monkeypatch.setattr(vision, "unit_cards_present", lambda f: False)

    with pytest.raises(PilotAbort):
        c._on_unit_move()

    kinds = [e["kind"] for e in c.ledger.events]
    assert "board_resync" in kinds
    aborts = [e for e in c.ledger.events if e["kind"] == "pilot_abort"]
    assert aborts and aborts[0]["reason"] == "board_empty_after_resync"


def test_pilot_target_mismatch_without_switch_button_aborts(monkeypatch):
    advice = _advice(kind="attack", weapon="rifle", target_id=ENEMY_UID)
    c = _pilot_controller(monkeypatch, advice, specs={"ally_1": _spec()})
    c._on_unit_move()

    monkeypatch.setattr(vision, "attack_enabled", lambda f: True)
    monkeypatch.setattr(
        vision, "read_weapon_select_forecast",
        lambda f: _forecast(target_name_sig="0" * 16),
    )
    c._dispatched_mode = "label_weapon_select"

    with pytest.raises(PilotAbort):
        c._on_weapon_select()
    aborts = [e for e in c.ledger.events if e["kind"] == "pilot_abort"]
    assert aborts[0]["reason"] == "target_mismatch"
    assert aborts[0]["seen"] == "0" * 16


def test_pilot_weapon_not_lit_aborts(monkeypatch):
    advice = _advice(kind="attack", weapon="rifle", target_id=ENEMY_UID)
    c = _pilot_controller(monkeypatch, advice, specs={"ally_1": _spec()})
    c._on_unit_move()

    monkeypatch.setattr(vision, "attack_enabled", lambda f: False)
    c._dispatched_mode = "label_weapon_select"

    with pytest.raises(PilotAbort):
        c._on_weapon_select()
    assert [e["reason"] for e in c.ledger.events if e["kind"] == "pilot_abort"] == [
        "weapon_not_lit"
    ]


def test_pilot_disabled_leaves_greedy_untouched(monkeypatch):
    c = _pilot_controller(monkeypatch, _advice())
    c.pilot_enabled = False

    c._on_unit_move()

    assert controller_mod.WEAPON_SELECT_BTN in c.actuator.taps
    assert "pilot_plan" not in _kinds(c)

def _popup(**kw):
    base = dict(
        attacker_name_sig=ENEMY_SIG,
        defender_name_sig=OUR_SIG,
        available=("dodge", "defend"),
        support_defend_available=False,
    )
    base.update(kw)
    return vision.ReactionPopup(**base)


def test_reaction_popup_choice_taps_the_calibrated_option(monkeypatch):
    c = _pilot_controller(monkeypatch, None)
    monkeypatch.setattr(vision, "read_reaction_popup", lambda f: _popup())
    monkeypatch.setattr(
        advisor_mod,
        "advise_reaction",
        lambda *a, **k: type("R", (), {"stance": "dodge", "weapon": None,
                                       "support_defend": False, "value": 1.0})(),
    )
    monkeypatch.setitem(controller_mod.REACTION_OPTION_TAPS, "dodge", (500, 700))

    handled = c._maybe_handle_reaction(c.perception.capture())

    assert handled is True
    assert (500, 700) in c.actuator.taps
    choices = [e for e in c.ledger.events if e["kind"] == "reaction_choice"]
    assert choices and choices[0]["stance"] == "dodge"


def test_reaction_popup_without_calibrated_tap_aborts(monkeypatch):
    c = _pilot_controller(monkeypatch, None)
    monkeypatch.setattr(vision, "read_reaction_popup", lambda f: _popup())
    monkeypatch.setattr(
        advisor_mod,
        "advise_reaction",
        lambda *a, **k: type("R", (), {"stance": "dodge", "weapon": None,
                                       "support_defend": False, "value": 1.0})(),
    )

    with pytest.raises(PilotAbort):
        c._maybe_handle_reaction(c.perception.capture())

    aborts = [e for e in c.ledger.events if e["kind"] == "pilot_abort"]
    assert aborts and aborts[0]["reason"] == "reaction_taps_uncalibrated"


def test_reaction_popup_ungrounded_names_abort(monkeypatch):
    c = _pilot_controller(monkeypatch, None)
    monkeypatch.setattr(
        vision, "read_reaction_popup", lambda f: _popup(attacker_name_sig=None)
    )

    with pytest.raises(PilotAbort):
        c._maybe_handle_reaction(c.perception.capture())

    aborts = [e for e in c.ledger.events if e["kind"] == "pilot_abort"]
    assert aborts and aborts[0]["reason"] == "reaction_ungrounded"


def test_reaction_popup_in_greedy_mode_is_logged_not_handled(monkeypatch):
    c = _pilot_controller(monkeypatch, None)
    c.pilot_enabled = False
    monkeypatch.setattr(vision, "read_reaction_popup", lambda f: _popup())

    handled = c._maybe_handle_reaction(c.perception.capture())

    assert handled is False
    assert any(e["kind"] == "reaction_popup" for e in c.ledger.events)
