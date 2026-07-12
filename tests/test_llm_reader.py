"""LLM screen reader: advisory fallback perception. The contract under test
is safety, not intelligence -- it must rate-limit itself, survive garbage
output and dead servers, and stay completely absent when disabled."""

import json

import cv2
import numpy as np

from ggge_ai.perception.llm import MAX_EDGE, LlmScreenReader, ScreenReading


def _frame():
    return np.zeros((1080, 2340, 3), np.uint8)


def _reader(reply, **kw):
    calls = []

    def transport(url, payload, timeout_s):
        calls.append(payload)
        return reply

    reader = LlmScreenReader(transport=transport, **kw)
    return reader, calls


def test_read_sends_one_downscaled_image_and_parses_the_reply():
    reply = json.dumps(
        {
            "scene": "battle map",
            "visible_text": ["我軍回合", "TURN 1"],
            "dialog": False,
            "buttons": ["MENU"],
            "suggestion": "wait",
        }
    )
    reader, calls = _reader(reply)
    reading = reader.read(_frame())

    assert reading is not None
    assert reading.scene == "battle map"
    assert reading.visible_text == ["我軍回合", "TURN 1"]
    assert reading.dialog is False
    assert "我軍回合" in reading.summary()

    payload = calls[0]
    assert payload["format"] == "json"
    assert payload["options"]["temperature"] == 0
    images = payload["messages"][0]["images"]
    assert len(images) == 1
    import base64

    decoded = cv2.imdecode(
        np.frombuffer(base64.b64decode(images[0]), np.uint8), cv2.IMREAD_COLOR
    )
    assert max(decoded.shape[:2]) <= MAX_EDGE


def test_missing_keys_default_instead_of_raising():
    reader, _ = _reader(json.dumps({"scene": "?"}))
    reading = reader.read(_frame())
    assert reading == ScreenReading(
        scene="?", visible_text=[], dialog=False, buttons=[], suggestion="",
        latency_s=reading.latency_s,
    )


def test_garbage_reply_returns_none():
    reader, _ = _reader("not json at all")
    assert reader.read(_frame()) is None
    reader, _ = _reader(json.dumps(["a", "list"]))
    reader.min_interval_s = 0
    assert reader.read(_frame()) is None


def test_transport_failure_returns_none_instead_of_raising():
    def transport(url, payload, timeout_s):
        raise OSError("server gone")

    reader = LlmScreenReader(transport=transport)
    assert reader.read(_frame()) is None


def test_rate_limit_skips_until_forced():
    reader, calls = _reader(json.dumps({"scene": "x"}), min_interval_s=3600)
    assert reader.read(_frame()) is not None
    assert reader.read(_frame()) is None
    assert len(calls) == 1
    assert reader.read(_frame(), force=True) is not None
    assert len(calls) == 2


def test_from_env_disabled_via_ggge_llm(monkeypatch):
    monkeypatch.setenv("GGGE_LLM", "0")
    assert LlmScreenReader.from_env() is None


def test_from_env_disabled_when_server_unreachable(monkeypatch):
    monkeypatch.delenv("GGGE_LLM", raising=False)
    monkeypatch.setenv("GGGE_LLM_URL", "http://127.0.0.1:1")
    assert LlmScreenReader.from_env() is None


def test_unrecognized_scene_gets_an_llm_read_before_the_neutral_tap(monkeypatch):
    from ggge_ai.battle import controller as controller_mod
    from ggge_ai.battle import vision
    from ggge_ai.battle.controller import ManualBattleController
    from ggge_ai.battle.ledger import BattleLedger

    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(vision, "locate_dialog_cursor", lambda frame: None)

    class _P:
        def capture(self):
            return _frame()

    class _A:
        def __init__(self):
            self.taps = []

        def tap(self, x, y):
            self.taps.append((x, y))

    reader, _ = _reader(json.dumps({"scene": "mystery", "suggestion": "tap"}))
    c = ManualBattleController(perception=_P(), actuator=_A(), ledger=BattleLedger(), llm=reader)

    for _ in range(controller_mod.NEUTRAL_TAP_AFTER_MISSES):
        c._on_not_actionable()

    kinds = [e["kind"] for e in c.ledger.events]
    assert "llm_read" in kinds
    read_event = next(e for e in c.ledger.events if e["kind"] == "llm_read")
    assert read_event["scene"] == "mystery"
    assert read_event["reason"] == "unrecognized_scene"
    assert kinds.index("llm_read") < kinds.index("neutral_tap")


def test_distractor_labelled_scene_skips_the_llm(monkeypatch):
    from ggge_ai.battle import controller as controller_mod
    from ggge_ai.battle import vision
    from ggge_ai.battle.controller import ManualBattleController
    from ggge_ai.battle.ledger import BattleLedger

    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(vision, "locate_dialog_cursor", lambda frame: None)

    class _P:
        def capture(self):
            return _frame()

    class _A:
        def tap(self, x, y):
            pass

    reader, calls = _reader(json.dumps({"scene": "x"}))
    c = ManualBattleController(perception=_P(), actuator=_A(), ledger=BattleLedger(), llm=reader)
    c._last_probe = {"label_enemy_turn": 0.99}

    for _ in range(controller_mod.NEUTRAL_TAP_AFTER_MISSES):
        c._on_not_actionable()

    assert calls == []
