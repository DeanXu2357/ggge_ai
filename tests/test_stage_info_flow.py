"""AdvanceStageInfo flow action: force AUTO to manual, archive the conditions
frame to the battle ledger, and tap through to the battle. The ledger opened
here must be the same one ManualBattle uses, so both land in one battle file."""

from types import SimpleNamespace

import numpy as np

from ggge_ai.agent.blackboard import RunBlackboard
from ggge_ai.battle import controller as controller_mod
from ggge_ai.core.action import ExecutionContext
from ggge_ai.domain import screens
from ggge_ai.domain.actions import flow
from ggge_ai.domain.actions.flow import AdvanceStageInfo, CLEAR_STAGE_ACTIONS


class _Perception:
    def __init__(self, screen_seq):
        self.seq = list(screen_seq)
        self.i = 0

    def observe(self):
        s = self.seq[min(self.i, len(self.seq) - 1)]
        self.i += 1
        return SimpleNamespace(screen=s, screen_confidence=0.95)

    def capture(self):
        return np.zeros((1080, 2340, 3), np.uint8)

    def probe(self, ids):
        return {}


class _Actuator:
    def __init__(self):
        self.taps = []

    def tap(self, x, y):
        self.taps.append((x, y))


def test_advance_stage_info_records_frame_and_advances(monkeypatch):
    monkeypatch.setattr(controller_mod, "ensure_manual_auto", lambda *a, **k: True)
    monkeypatch.setattr(flow.time, "sleep", lambda *a, **k: None)

    bb = RunBlackboard(goal="clear")
    perc = _Perception([screens.STORY])  # screen has already left stage_info
    act = _Actuator()
    ctx = ExecutionContext(actuator=act, perception=perc, game_state=None, extras={"blackboard": bb})

    assert AdvanceStageInfo().execute(ctx) is True
    assert flow.STAGE_INFO_TAP in act.taps
    ledger = bb.pending_ledger
    assert ledger is not None
    assert any(e["kind"] == "stage_info" for e in ledger.events)


def test_advance_stage_info_is_in_clear_plan():
    names = [a.name for a in CLEAR_STAGE_ACTIONS]
    assert "advance_stage_info" in names
    # it must sit on the path between launching and the story/battle
    assert names.index("launch_sortie") < names.index("advance_stage_info")
    assert names.index("advance_stage_info") < names.index("manual_battle")


def test_stage_info_ledger_is_reused_by_battle():
    bb = RunBlackboard(goal="clear")
    opened = bb.open_ledger()  # opened at stage_info
    claimed = bb.take_ledger()  # claimed by the battle
    assert claimed is opened
    assert bb.pending_ledger is None
    assert len(bb.ledgers) == 1


def test_battle_opens_fresh_ledger_when_no_stage_info():
    bb = RunBlackboard(goal="clear")
    claimed = bb.take_ledger()
    assert claimed is not None
    assert bb.pending_ledger is None
    assert len(bb.ledgers) == 1
