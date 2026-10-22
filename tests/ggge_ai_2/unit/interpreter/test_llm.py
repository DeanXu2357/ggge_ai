import base64
import json
import logging
from dataclasses import dataclass, field
from typing import Any, cast

import anthropic
import cv2
import numpy as np
import pytest

from ggge_ai_2.interpreter.contract import Screen, Situation
from ggge_ai_2.interpreter.llm import ANSWER_SCHEMA, LlmInterpreter
from ggge_ai_2.stream.contract import Frame


@dataclass
class _Block:
    text: str
    type: str = "text"


@dataclass
class _Usage:
    input_tokens: int = 100
    cache_read_input_tokens: int | None = 2000


@dataclass
class _Response:
    content: list[_Block]
    stop_reason: str = "end_turn"
    usage: _Usage = field(default_factory=_Usage)


@dataclass
class _Messages:
    response: _Response
    calls: list[dict[str, Any]] = field(default_factory=lambda: [])

    def create(self, **kwargs: Any) -> _Response:
        self.calls.append(kwargs)
        return self.response


@dataclass
class _Client:
    messages: _Messages


def _answer(screen: str, auto: bool | None = None) -> _Response:
    text = json.dumps({"screen": screen, "auto": auto, "reason": "test"})
    return _Response([_Block(text)])


def _interpreter(response: _Response) -> tuple[LlmInterpreter, _Messages]:
    messages = _Messages(response)
    client = cast(anthropic.Anthropic, _Client(messages))
    return LlmInterpreter(client=client, system="system text"), messages


def _frame() -> Frame:
    return Frame(image=np.zeros((1080, 2340, 3), dtype=np.uint8), captured_at=0.0, seq=7)


CANDIDATES = frozenset({Screen.SORTIE_PREP, Screen.BATTLE_MAIN_SETTING})


def test_known_screen_returns_situation_with_auto() -> None:
    interpreter, _ = _interpreter(_answer("player_phase_overview", auto=True))

    situation = interpreter.interpret(_frame(), CANDIDATES)

    assert situation == Situation(7, Screen.PLAYER_PHASE_OVERVIEW, True)


def test_null_auto_passes_through() -> None:
    interpreter, _ = _interpreter(_answer("sortie_prep"))

    assert interpreter.interpret(_frame(), CANDIDATES) == Situation(7, Screen.SORTIE_PREP, None)


def test_unknown_returns_none() -> None:
    interpreter, _ = _interpreter(_answer("unknown"))

    assert interpreter.interpret(_frame(), CANDIDATES) is None


@pytest.mark.parametrize("screen", ["undefined", "title_screen", ""])
def test_value_outside_screen_returns_none(screen: str) -> None:
    interpreter, _ = _interpreter(_answer(screen))

    assert interpreter.interpret(_frame(), CANDIDATES) is None


def test_refusal_returns_none(caplog: pytest.LogCaptureFixture) -> None:
    interpreter, _ = _interpreter(_Response([], stop_reason="refusal"))

    with caplog.at_level(logging.WARNING):
        assert interpreter.interpret(_frame(), CANDIDATES) is None
    assert any(r.levelno == logging.WARNING for r in caplog.records)


@pytest.mark.parametrize(
    "response",
    [
        _Response([], stop_reason="end_turn"),
        _Response([_Block('{"reason": "the title rea')], stop_reason="max_tokens"),
    ],
    ids=["no_text_block", "truncated_json"],
)
def test_unreadable_answer_returns_none(
    response: _Response, caplog: pytest.LogCaptureFixture
) -> None:
    interpreter, _ = _interpreter(response)

    with caplog.at_level(logging.WARNING):
        assert interpreter.interpret(_frame(), CANDIDATES) is None
    record = next(r for r in caplog.records if r.getMessage() == "llm answer unreadable")
    assert record.levelno == logging.WARNING
    assert record.__dict__["frame_seq"] == 7
    assert record.__dict__["stop_reason"] == response.stop_reason


def test_schema_lists_reason_first() -> None:
    assert list(cast(dict[str, object], ANSWER_SCHEMA["properties"])) == [
        "reason",
        "screen",
        "auto",
    ]
    assert ANSWER_SCHEMA["required"] == ["reason", "screen", "auto"]


def test_answer_is_logged_with_usage(caplog: pytest.LogCaptureFixture) -> None:
    interpreter, _ = _interpreter(_answer("sortie_prep", auto=False))

    with caplog.at_level(logging.INFO):
        interpreter.interpret(_frame(), CANDIDATES)

    record = next(r for r in caplog.records if r.getMessage() == "llm answer")
    assert record.__dict__["frame_seq"] == 7
    assert record.__dict__["screen"] == "sortie_prep"
    assert record.__dict__["auto"] is False
    assert record.__dict__["cache_read_input_tokens"] == 2000
    assert record.__dict__["input_tokens"] == 100


def test_request_carries_image_candidates_cached_system_and_low_effort() -> None:
    interpreter, messages = _interpreter(_answer("sortie_prep"))

    interpreter.interpret(_frame(), CANDIDATES)

    (call,) = messages.calls
    assert call["model"] == "claude-haiku-5-5"
    assert call["system"] == [
        {"type": "text", "text": "system text", "cache_control": {"type": "ephemeral"}}
    ]
    assert call["output_config"]["effort"] == "low"
    assert call["output_config"]["format"]["type"] == "json_schema"
    image, text = call["messages"][0]["content"]
    assert image["type"] == "image"
    assert image["source"]["type"] == "base64"
    assert image["source"]["media_type"] == "image/jpeg"
    assert text == {
        "type": "text",
        "text": "Candidate screens: battle_main_setting, sortie_prep",
    }


def test_image_is_downscaled_to_width() -> None:
    interpreter, messages = _interpreter(_answer("sortie_prep"))

    interpreter.interpret(_frame(), CANDIDATES)

    data = messages.calls[0]["messages"][0]["content"][0]["source"]["data"]
    jpeg = np.frombuffer(base64.standard_b64decode(data), dtype=np.uint8)
    image = cv2.imdecode(jpeg, cv2.IMREAD_COLOR)
    assert image is not None
    assert image.shape[:2] == (540, 1170)
