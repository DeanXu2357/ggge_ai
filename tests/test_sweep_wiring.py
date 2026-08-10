"""sweep_scan 的名冊接線：段序、停點、離線步，以及我方出卡的讀值欄。

裝置與採集器整組換成假件，一格都不點；離線步也只驗有沒有被叫到。
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from ggge_ai.runtime import entry, screens, sweep
from ggge_ai.runtime.coverage import WorldGrid
from ggge_ai.runtime.journal import Journal
from ggge_ai.stage import roster_offline
from scripts import sweep_scan
from scripts.sweep_scan import IN_BATTLE_STAGES, STAGES, SweepRun

GRID = WorldGrid(phase=(0.0, 0.0), col_pitch=100.0, row_pitch=100.0)


def _blank() -> np.ndarray:
    return np.zeros((1080, 2340, 3), np.uint8)


def _png() -> bytes:
    return cv2.imencode(".png", _blank())[1].tobytes()


def _passing() -> entry.GateReport:
    report = entry.GateReport()
    report.add("stub", "ok")
    return report


def _entries(journal: Journal) -> list[dict]:
    return journal.entries()


def _stages(journal: Journal) -> list[str]:
    return [item["name"] for item in _entries(journal) if item["kind"] == "stage"]


class FakeCapture:
    """RosterCapture 的替身：記下注入了什麼，一下都不點。"""

    built: list["FakeCapture"] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.ran = 0
        FakeCapture.built.append(self)

    def run(self):
        self.ran += 1
        return []


@pytest.fixture(autouse=True)
def _no_real_capture(monkeypatch):
    FakeCapture.built = []
    monkeypatch.setattr(sweep_scan, "RosterCapture", FakeCapture)


def wired_run(tmp_path, monkeypatch, **kwargs) -> SweepRun:
    """run() 的骨架：閘門與掃描段全部短路，只留段序與名冊段。"""
    for name in ("select_stage", "open_sortie_prep", "sortie", "advance_to_map"):
        monkeypatch.setattr(entry, name, lambda *args, **kw: _passing())
    journal = Journal(tmp_path / "sweep.jsonl")
    camera = SimpleNamespace(grab=_blank, keep=lambda label: None, shots=0, raw=None)
    device = SimpleNamespace(
        tap=lambda x, y, intent="": None,
        swipe=lambda x1, y1, x2, y2, duration_s=0.3: None,
        ensure_unlocked=lambda force=False: None,
    )
    run = SweepRun(
        device=device,
        camera=camera,
        journal=journal,
        executor=None,
        driver=None,
        perceiver=None,
        gate=None,
        identifier=None,
        sleep=lambda seconds: None,
        **kwargs,
    )
    run.ledger = sweep.SweepLedger(grid=GRID)
    run.perform = lambda action, label: None
    run.observe = lambda label: SimpleNamespace(
        evidence={"grid_on": True, "roster_strip": screens.ROSTER_COLLAPSED}
    )
    run.zero = lambda: None
    run.tour = lambda: None
    run.summarize = lambda: None
    return run


def test_the_roster_stage_comes_after_the_sweep_and_still_counts_as_in_battle():
    assert STAGES[-2:] == ("sweep", "roster")
    assert "roster" in IN_BATTLE_STAGES


def test_stopping_after_the_sweep_never_opens_the_roster(tmp_path, monkeypatch):
    run = wired_run(tmp_path, monkeypatch, stop_after="sweep")

    run.run()

    assert _stages(run.journal)[-1] == "sweep"
    assert FakeCapture.built == []


@pytest.mark.parametrize("stop_after", [None, "roster"])
def test_the_roster_stage_runs_and_books_the_ledger(tmp_path, monkeypatch, stop_after):
    run = wired_run(tmp_path, monkeypatch, stop_after=stop_after)
    run.ledger.record((3, 4), sweep.ENEMY)

    run.run()

    assert _stages(run.journal)[-1] == "roster"
    assert [capture.ran for capture in FakeCapture.built] == [1]
    injected = FakeCapture.built[0].kwargs
    assert injected["grab"] is run.camera.grab
    assert injected["keep"] is run.camera.keep
    assert injected["tap"] is run.device.tap
    assert injected["swipe"] is run.device.swipe
    assert injected["journal"] is run.journal
    dumps = [item for item in _entries(run.journal) if item["kind"] == "ledger_dump"]
    assert dumps[0]["cells"] == [[3, 4, sweep.ENEMY]]


def test_the_roster_stage_survives_a_capture_that_blows_up(tmp_path, monkeypatch):
    run = wired_run(tmp_path, monkeypatch)

    def explode(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(sweep_scan, "RosterCapture", explode)

    run.run()

    kinds = [item["kind"] for item in _entries(run.journal)]
    assert "roster_stage_failed" in kinds
    assert "ledger_dump" in kinds
    assert _stages(run.journal)[-1] == "roster"


def test_no_roster_skips_the_stage_entirely(tmp_path, monkeypatch):
    run = wired_run(tmp_path, monkeypatch, roster=False)

    run.run()

    assert _stages(run.journal)[-1] == "sweep"
    assert FakeCapture.built == []
    assert [item for item in _entries(run.journal) if item["kind"] == "ledger_dump"] == []


def test_the_ledger_dump_is_what_the_offline_facts_reader_expects(tmp_path, monkeypatch):
    run = wired_run(tmp_path, monkeypatch)
    run.ledger.record((3, 4), sweep.ENEMY)
    run.ledger.record((5, 6), sweep.ALLY)
    run.journal.record("verdict", cell=[3, 4], verdict=sweep.ENEMY, hp=120, en=45)

    run.run()

    facts = roster_offline.sweep_facts(_entries(run.journal))
    assert facts.source == "ledger_dump"
    assert {fact.cell: fact.verdict for fact in facts.cells} == {
        (3, 4): sweep.ENEMY,
        (5, 6): sweep.ALLY,
    }
    assert facts.enemy_cells[0].hp == 120
    assert facts.enemy_cells[0].en == 45


def shift_run(tmp_path, monkeypatch) -> SweepRun:
    run = wired_run(tmp_path, monkeypatch)
    run.camera.raw = _png()
    run.escape = lambda: None
    run.relocate = lambda candidate=None: None
    return run


def _verdicts(journal: Journal) -> list[dict]:
    return [item for item in journal.entries() if item["kind"] == "verdict"]


def test_our_own_card_books_its_hp_and_en(tmp_path, monkeypatch):
    run = shift_run(tmp_path, monkeypatch)
    monkeypatch.setattr(
        sweep_scan.vision,
        "read_ally_summary",
        lambda frame: SimpleNamespace(name_sig="sig-a", hp=210, en=90),
    )

    run.sentence_shift(
        sweep.TapTarget((3, 4), (350.0, 450.0)), sweep.TapOutcome(sweep.TAP_SHIFTED)
    )

    booked = _verdicts(run.journal)[0]
    assert (booked["hp"], booked["en"]) == (210, 90)
    assert booked["verdict"] == sweep.ALLY


def test_a_read_that_blows_up_leaves_the_values_blank_and_the_verdict_intact(
    tmp_path, monkeypatch
):
    run = shift_run(tmp_path, monkeypatch)

    def explode(frame):
        raise ValueError("no anchor")

    monkeypatch.setattr(sweep_scan.vision, "read_ally_summary", explode)

    run.sentence_shift(
        sweep.TapTarget((3, 4), (350.0, 450.0)), sweep.TapOutcome(sweep.TAP_SHIFTED)
    )

    booked = _verdicts(run.journal)[0]
    assert booked["hp"] is None and booked["en"] is None
    assert run.ledger.verdict((3, 4)) == sweep.ALLY


def _args(monkeypatch, *extra) -> object:
    monkeypatch.setattr(sys, "argv", ["sweep_scan.py", "--stage-node", "544,667", *extra])
    return sweep_scan.parse_args()


def fake_run() -> SimpleNamespace:
    calls: list[str] = []
    return SimpleNamespace(
        calls=calls,
        run=lambda: calls.append("run"),
        abandon=lambda: calls.append("abandon"),
        camera=SimpleNamespace(keep=lambda label: None),
    )


def offline_spy(monkeypatch) -> list:
    seen: list = []
    monkeypatch.setattr(sweep_scan.OllamaPanelTextReader, "from_env", classmethod(lambda cls: None))
    monkeypatch.setattr(
        sweep_scan.roster_offline,
        "run_offline",
        lambda run_dir, **kwargs: (seen.append((run_dir, kwargs)), 0)[1],
    )
    return seen


def test_the_default_run_abandons_and_then_assembles_offline(tmp_path, monkeypatch):
    args = _args(monkeypatch)
    seen = offline_spy(monkeypatch)
    journal = Journal(tmp_path / "sweep.jsonl")
    run = fake_run()

    assert sweep_scan.drive(args, run, journal, tmp_path) == 0
    assert run.calls == ["run", "abandon"]
    assert seen and seen[0][0] == tmp_path


def test_stopping_after_the_sweep_leaves_the_offline_step_alone(tmp_path, monkeypatch):
    args = _args(monkeypatch, "--stop-after", "sweep")
    seen = offline_spy(monkeypatch)
    journal = Journal(tmp_path / "sweep.jsonl")
    run = fake_run()

    assert sweep_scan.drive(args, run, journal, tmp_path) == 0
    assert run.calls == ["run", "abandon"]
    assert seen == []


def test_no_roster_drops_the_offline_step(tmp_path, monkeypatch):
    args = _args(monkeypatch, "--no-roster")
    seen = offline_spy(monkeypatch)
    journal = Journal(tmp_path / "sweep.jsonl")
    run = fake_run()

    assert sweep_scan.drive(args, run, journal, tmp_path) == 0
    assert seen == []


def test_a_failed_offline_step_does_not_change_the_exit_code(tmp_path, monkeypatch):
    args = _args(monkeypatch)
    offline_spy(monkeypatch)

    def explode(run_dir, **kwargs):
        raise RuntimeError("no frames")

    monkeypatch.setattr(sweep_scan.roster_offline, "run_offline", explode)
    journal = Journal(tmp_path / "sweep.jsonl")

    assert sweep_scan.drive(args, fake_run(), journal, tmp_path) == 0
    assert [item["kind"] for item in journal.entries() if item["kind"].startswith("intel_")] == [
        "intel_offline_failed"
    ]
