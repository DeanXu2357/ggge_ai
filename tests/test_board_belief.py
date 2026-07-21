"""Turn-boundary board-belief snapshot (silent-events batch A): the
controller serializes tracker.beliefs into one ledger event at each our-turn
hub, exactly once per turn including turn 1, so the offline audit/closure
layers can replay carried HP/EN plus its freshness. Pure-offline harness --
in-memory ledger, stubbed hub steps, monkeypatched vision reads."""

import json

import numpy as np

from ggge_ai.battle import vision
from ggge_ai.battle.controller import ManualBattleController
from ggge_ai.battle.ledger import BattleLedger
from ggge_ai.battle.state import Faction
from ggge_ai.battle.tracker import UnitBelief


class _Perception:
    def capture(self):
        return np.zeros((1080, 2340, 3), np.uint8)


class _Actuator:
    def tap(self, x, y):
        pass


def _controller(ledger: BattleLedger | None = None) -> ManualBattleController:
    c = ManualBattleController(
        perception=_Perception(),
        actuator=_Actuator(),
        ledger=ledger or BattleLedger(),
    )
    # the snapshot seam is under test; neutralize the heavy hub steps around it
    c._guard_auto = lambda: None
    c._snapshot_factions = lambda frame: None
    c._scout = lambda frame: None
    c._ensure_stage_definition = lambda frame: None
    c._refresh_sig_positions = lambda frame: None
    c._consult_advisor = lambda: None
    c._probe_after_select = lambda *a, **k: None
    return c


def _seed_beliefs(c: ManualBattleController) -> None:
    c.tracker.beliefs["e01"] = UnitBelief(
        sig="e", faction=Faction.ENEMY, hp=8000, en=120,
        world_pos=(400.0, 20.0), pos_turn=1, hp_turn=1, source="forecast",
    )
    # world_pos None and a definition HP never screen-confirmed (hp_turn 0)
    c.tracker.beliefs["a01"] = UnitBelief(
        sig="a", faction=Faction.ALLY, hp=30000, en=250,
        world_pos=None, hp_turn=0, source="definition",
    )


def test_snapshot_event_shape_tolerates_none_world_pos():
    c = _controller()
    _seed_beliefs(c)
    c.tracker.turn = 2

    c._snapshot_board_belief()

    ev = c.ledger.events[-1]
    assert ev["kind"] == "board_belief"
    units = {u["uid"]: u for u in ev["units"]}
    assert set(units) == {"e01", "a01"}
    e = units["e01"]
    assert e["faction"] == "enemy"
    assert e["world_pos"] == [400.0, 20.0]
    assert (e["hp"], e["en"], e["alive"], e["source"], e["hp_turn"]) == (
        8000, 120, True, "forecast", 1,
    )
    a = units["a01"]
    assert a["faction"] == "ally"
    assert a["world_pos"] is None
    assert a["hp_turn"] == 0


def test_snapshot_carries_no_frame():
    c = _controller()
    _seed_beliefs(c)
    c._snapshot_board_belief()
    assert "frame" not in c.ledger.events[-1]


def test_snapshot_serializes_to_jsonl(tmp_path):
    stream = tmp_path / "battle_01.jsonl"
    c = _controller(BattleLedger(stream_path=stream))
    _seed_beliefs(c)

    c._snapshot_board_belief()

    ev = json.loads(stream.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert ev["kind"] == "board_belief"
    a01 = next(u for u in ev["units"] if u["uid"] == "a01")
    assert a01["world_pos"] is None


def test_board_belief_once_per_turn_including_turn_one(monkeypatch):
    c = _controller()
    _seed_beliefs(c)
    turn = {"n": 1}
    monkeypatch.setattr(vision, "unit_cards_present", lambda f: True)
    monkeypatch.setattr(vision, "count_unit_cards", lambda f: 3)
    monkeypatch.setattr(vision, "read_turn_number", lambda f: turn["n"])
    monkeypatch.setattr(vision, "crop_turn_marker", lambda f: None)

    c._on_our_turn()  # turn 1, first hub visit
    c._on_our_turn()  # turn 1, second hub visit -- gate already claimed
    turn["n"] = 2
    c._on_our_turn()  # turn 2, gate re-armed on the boundary

    bb = [e for e in c.ledger.events if e["kind"] == "board_belief"]
    assert [e["turn"] for e in bb] == [1, 2]
