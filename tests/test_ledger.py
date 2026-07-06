import json

import numpy as np
import pytest

from ggge_ai.agent.blackboard import RunBlackboard
from ggge_ai.battle.controller import ManualBattleController
from ggge_ai.battle.ledger import BattleLedger
from ggge_ai.core.action import ExecutionContext
from ggge_ai.domain.actions.flow import ManualBattle


def _frame(h: int = 120, w: int = 200) -> np.ndarray:
    return np.random.randint(0, 255, (h, w, 3), dtype=np.uint8)


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


def test_manual_battle_archives_on_interrupt(tmp_path, monkeypatch):
    def interrupted_run(self):
        self.ledger.record("select_unit")
        raise KeyboardInterrupt

    monkeypatch.setattr(ManualBattleController, "run", interrupted_run)
    bb = RunBlackboard(goal="test", out_dir=tmp_path)
    ctx = ExecutionContext(actuator=object(), perception=object(), extras={"blackboard": bb})

    with pytest.raises(KeyboardInterrupt):
        ManualBattle().execute(ctx)

    lines = [json.loads(x) for x in (tmp_path / "battle_01.jsonl").read_text().splitlines()]
    assert [e["kind"] for e in lines] == ["select_unit", "finish"]
    assert lines[-1]["outcome"] == "interrupted"
    assert bb.ledgers[0].outcome == "interrupted"


def test_decision_events_save_frame_files(tmp_path):
    frames_dir = tmp_path / "frames" / "battle_01"
    ledger = BattleLedger(frames_dir=frames_dir, frame_rel_prefix="frames/battle_01")
    ledger.record("select_unit", frame=_frame())
    ledger.record("move", frame=_frame(), basis="enemy_onscreen", target=(3, 4), cell=(2, 3))
    ledger.record("attack", frame=_frame(), slot=1)

    for e in ledger.events:
        rel = e["frame"]
        assert rel.startswith("frames/battle_01/")
        assert rel.endswith(".jpg")
        assert (tmp_path / rel).exists()

    names = [e["frame"].rsplit("/", 1)[-1] for e in ledger.events]
    assert names == [
        "t0000_turn1_select_unit.jpg",
        "t0001_turn1_move.jpg",
        "t0002_turn1_attack.jpg",
    ]


def test_frame_is_downscaled_to_max_edge(tmp_path):
    import cv2

    from ggge_ai.battle.ledger import FRAME_MAX_EDGE

    frames_dir = tmp_path / "frames"
    ledger = BattleLedger(frames_dir=frames_dir, frame_rel_prefix="frames")
    ledger.record("attack", frame=_frame(1080, 2340), slot=0)

    saved = cv2.imread(str(tmp_path / ledger.events[0]["frame"]))
    assert max(saved.shape[:2]) == FRAME_MAX_EDGE


def test_non_decision_events_have_no_frame(tmp_path):
    frames_dir = tmp_path / "frames"
    ledger = BattleLedger(frames_dir=frames_dir, frame_rel_prefix="frames")
    ledger.snapshot(allies=[(1, 2)], enemies=[(3, 4)], third_party=[])
    ledger.record("engagement_confirm", frame=_frame())

    for e in ledger.events:
        assert "frame" not in e
    assert not frames_dir.exists()


def test_frame_column_null_when_no_frame_passed(tmp_path):
    ledger = BattleLedger(frames_dir=tmp_path / "frames", frame_rel_prefix="frames")
    ledger.record("standby", reason="out_of_range")
    assert ledger.events[0]["frame"] is None


def test_save_failure_records_event_with_null_frame(tmp_path):
    frames_dir = tmp_path / "frames"
    ledger = BattleLedger(frames_dir=frames_dir, frame_rel_prefix="frames")
    ledger.record("move", frame=object(), cell=(1, 1))

    assert ledger.events[0]["kind"] == "move"
    assert ledger.events[0]["frame"] is None
    assert ledger.events[0]["cell"] == (1, 1)


def test_save_failure_on_unwritable_dir_does_not_raise(tmp_path):
    blocker = tmp_path / "frames"
    blocker.write_text("not a directory")
    ledger = BattleLedger(frames_dir=blocker / "battle_01", frame_rel_prefix="frames/battle_01")
    ledger.record("attack", frame=_frame(), slot=0)

    assert ledger.events[0]["frame"] is None


def test_new_ledger_assigns_incrementing_frames_dir(tmp_path):
    bb = RunBlackboard(goal="test", out_dir=tmp_path)
    first = bb.new_ledger()
    second = bb.new_ledger()

    assert first.frames_dir == tmp_path / "frames" / "battle_01"
    assert first.frame_rel_prefix == "frames/battle_01"
    assert second.frames_dir == tmp_path / "frames" / "battle_02"
    assert second.frame_rel_prefix == "frames/battle_02"
