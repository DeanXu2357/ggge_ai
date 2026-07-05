import json

from ggge_ai.agent.blackboard import RunBlackboard
from ggge_ai.battle.ledger import BattleLedger


def test_ledger_records_turns_and_summary():
    ledger = BattleLedger()
    ledger.snapshot(allies=[(1, 2)], enemies=[(3, 4), (5, 6)], third_party=[])
    ledger.record("move", basis="enemy_arc", target=(3, 4), cell=(2, 3))
    ledger.record("attack", slot=1)
    ledger.next_turn()
    ledger.record("standby", reason="out_of_range")
    ledger.finish("battle_result")

    s = ledger.summary()
    assert s["outcome"] == "battle_result"
    assert s["turns"] == 2
    assert s["first_factions"] == {"allies": 1, "enemies": 2, "third_party": 0}
    assert s["event_counts"]["attack"] == 1
    assert ledger.events[-2]["turn"] == 2


def test_blackboard_archives_jsonl(tmp_path):
    bb = RunBlackboard(goal="test", out_dir=tmp_path)
    ledger = bb.new_ledger()
    ledger.record("select_unit")
    ledger.finish("battle_result")
    bb.archive(ledger)

    lines = [json.loads(x) for x in (tmp_path / "battle_01.jsonl").read_text().splitlines()]
    assert [e["kind"] for e in lines] == ["select_unit", "finish"]
    assert all("t" in e and "turn" in e for e in lines)
