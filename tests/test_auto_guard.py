"""AUTO guard with expectation-transition verification: every tap on the AUTO
toggle must be followed by an observed chip-state change (act -> verify ->
retry), and the sortie flow refuses to advance while the chip is stuck -- the
20260711 battle was tainted exactly because the old guard gave up silently."""

import numpy as np

from ggge_ai.battle import controller as controller_mod
from ggge_ai.battle import vision
from ggge_ai.battle.controller import (
    AUTO_BUTTON,
    ManualBattleController,
    force_manual_auto,
    read_auto_chip,
)
from ggge_ai.battle.ledger import BattleLedger
from ggge_ai.goap.action import ExecutionContext
from ggge_ai.domain.actions.flow import STAGE_INFO_TAP, AdvanceStageInfo
from ggge_ai.perception.base import Bbox, UiElement


class _FakeTime:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class _Chip:
    """The AUTO toggle: full -> enemy -> manual, one step per accepted tap."""

    SEQUENCE = ("btn_auto_full", "btn_auto_enemy", "btn_auto_manual")

    def __init__(self, state="btn_auto_full", eat_first_n_taps=0):
        self.idx = self.SEQUENCE.index(state)
        self.eaten_budget = eat_first_n_taps
        self.taps = 0

    @property
    def state(self):
        return self.SEQUENCE[self.idx]

    def tap(self):
        self.taps += 1
        if self.eaten_budget > 0:
            self.eaten_budget -= 1
            return
        self.idx = min(self.idx + 1, len(self.SEQUENCE) - 1)


class _ChipPerception:
    def __init__(self, chip: _Chip | None):
        self.chip = chip

    def probe(self, ids):
        if self.chip is None:
            return {}
        state = self.chip.state
        return {state: UiElement(id=state, bbox=Bbox(1800, 40, 40, 30), confidence=0.9)}

    def capture(self):
        return np.zeros((1080, 2340, 3), np.uint8)

    def observe(self):
        raise AssertionError("observe should not run in these tests")


class _ChipActuator:
    def __init__(self, chip: _Chip | None):
        self.chip = chip
        self.taps = []

    def tap(self, x, y):
        self.taps.append((x, y))
        if self.chip is not None and (x, y) == AUTO_BUTTON:
            self.chip.tap()

    def swipe(self, *args):
        pass


def _patch_time(monkeypatch):
    fake = _FakeTime()
    monkeypatch.setattr(controller_mod, "time", fake)
    return fake


def test_force_manual_cycles_full_to_manual_with_verified_transitions(monkeypatch):
    _patch_time(monkeypatch)
    chip = _Chip("btn_auto_full")
    result = force_manual_auto(_ChipPerception(chip), _ChipActuator(chip), timeout_s=30.0)
    assert result == "manual"
    assert chip.taps == 2


def test_force_manual_returns_absent_when_chip_never_seen(monkeypatch):
    _patch_time(monkeypatch)
    actuator = _ChipActuator(None)
    result = force_manual_auto(_ChipPerception(None), actuator, timeout_s=10.0)
    assert result == "absent"
    assert actuator.taps == []


def test_force_manual_retries_an_eaten_tap(monkeypatch):
    """A tap swallowed by the power-save lock leaves the chip unchanged; the
    verify step must notice and tap again instead of trusting the act."""
    _patch_time(monkeypatch)
    chip = _Chip("btn_auto_full", eat_first_n_taps=1)
    result = force_manual_auto(_ChipPerception(chip), _ChipActuator(chip), timeout_s=60.0)
    assert result == "manual"
    assert chip.taps == 3


def test_force_manual_unconfirmed_when_chip_is_stuck(monkeypatch):
    _patch_time(monkeypatch)
    chip = _Chip("btn_auto_full", eat_first_n_taps=10**6)
    result = force_manual_auto(_ChipPerception(chip), _ChipActuator(chip), timeout_s=20.0)
    assert result == "unconfirmed"
    assert chip.taps >= 2


def test_read_auto_chip_rejects_disagreeing_reads(monkeypatch):
    _patch_time(monkeypatch)

    class _Flicker(_ChipPerception):
        def __init__(self):
            super().__init__(_Chip("btn_auto_full"))
            self.calls = 0

        def probe(self, ids):
            self.calls += 1
            self.chip.idx = self.calls % 2
            return super().probe(ids)

    assert read_auto_chip(_Flicker()) is None


def _hub_controller(monkeypatch, chip):
    monkeypatch.setattr(vision, "unit_cards_present", lambda f: True)
    monkeypatch.setattr(vision, "crop_turn_marker", lambda f: np.zeros((36, 40), np.uint8))
    monkeypatch.setattr(vision, "turn_marker_changed", lambda a, b: False)
    c = ManualBattleController(
        perception=_ChipPerception(chip),
        actuator=_ChipActuator(chip),
        ledger=BattleLedger(),
    )
    c._scout = lambda frame: None
    c._snapshot_factions = lambda frame: None
    c._probe_after_select = lambda *a, **k: None
    c._turn_marker = np.zeros((36, 40), np.uint8)
    return c


def test_hub_guard_forces_a_stray_full_auto_back_to_manual(monkeypatch):
    _patch_time(monkeypatch)
    chip = _Chip("btn_auto_full")
    c = _hub_controller(monkeypatch, chip)
    c._on_our_turn()
    assert chip.state == "btn_auto_manual"
    guard_events = [e for e in c.ledger.events if e["kind"] == "auto_guard"]
    assert len(guard_events) == 1
    assert guard_events[0]["result"] == "manual"


def test_hub_guard_is_silent_when_already_manual(monkeypatch):
    _patch_time(monkeypatch)
    chip = _Chip("btn_auto_manual")
    c = _hub_controller(monkeypatch, chip)
    c._on_our_turn()
    assert chip.taps == 0
    assert all(e["kind"] != "auto_guard" for e in c.ledger.events)


def test_stage_info_refuses_to_advance_on_a_stuck_chip(monkeypatch):
    _patch_time(monkeypatch)
    import ggge_ai.domain.actions.flow as flow_mod

    monkeypatch.setattr(flow_mod, "time", _FakeTime())
    chip = _Chip("btn_auto_full", eat_first_n_taps=10**6)
    actuator = _ChipActuator(chip)
    ctx = ExecutionContext(actuator=actuator, perception=_ChipPerception(chip))
    ok = AdvanceStageInfo().execute(ctx)
    assert ok is False
    assert STAGE_INFO_TAP not in actuator.taps
