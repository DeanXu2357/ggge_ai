"""The engine shell through the real executable: envelope rules and the client."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from ggge_ai.engine.client import BattleEngine, EngineDead, EngineError, EngineTimeout
from ggge_ai.engine.contract import DECLARED_COMMANDS, PROTOCOL_VERSION, ErrorCode

IMPLEMENTED = {"hello", "ping", "load", "reach"}


def _script(path: Path, body: str) -> Path:
    path.write_text(f"#!{sys.executable}\nimport sys, time\n{body}\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _exchange(engine_executable: Path, *lines: str) -> tuple[list[dict], int]:
    process = subprocess.Popen(
        [str(engine_executable)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        bufsize=0,
    )
    out, _ = process.communicate("".join(f"{line}\n" for line in lines).encode(), timeout=30)
    return [json.loads(line) for line in out.splitlines() if line.strip()], process.returncode


def test_the_response_keeps_the_request_id_and_eof_stops_the_process(engine_executable):
    responses, status = _exchange(engine_executable, '{"id":"a1","cmd":"ping","payload":{}}')

    assert responses == [{"id": "a1", "ok": True, "payload": {}}]
    assert status == 0


def test_hello_lists_every_declared_command_in_order(engine_executable):
    responses, _ = _exchange(engine_executable, '{"id":"h1","cmd":"hello","payload":{}}')
    payload = responses[0]["payload"]

    assert payload["protocol"] == PROTOCOL_VERSION
    assert tuple(command["name"] for command in payload["commands"]) == DECLARED_COMMANDS
    assert {command["name"] for command in payload["commands"] if command["implemented"]} == (
        IMPLEMENTED
    )


def test_a_declared_command_with_no_handler_is_not_implemented(engine_executable):
    responses, _ = _exchange(
        engine_executable,
        '{"id":"d1","cmd":"act","payload":{}}',
        '{"id":"d2","cmd":"ping","payload":{}}',
    )

    assert responses[0]["id"] == "d1"
    assert responses[0]["ok"] is False
    assert responses[0]["error"]["code"] == ErrorCode.NOT_IMPLEMENTED
    assert responses[1]["ok"] is True


def test_an_unknown_command_is_refused(engine_executable):
    responses, _ = _exchange(
        engine_executable,
        '{"id":"u1","cmd":"teleport","payload":{}}',
        '{"id":"u2","cmd":"ping","payload":{}}',
    )

    assert responses[0]["id"] == "u1"
    assert responses[0]["error"]["code"] == ErrorCode.UNKNOWN_COMMAND
    assert responses[1]["ok"] is True


def test_a_malformed_line_is_bad_request_with_an_empty_id(engine_executable):
    responses, _ = _exchange(
        engine_executable,
        '{"id":"m1",',
        '{"id":"m2","cmd":"ping","payload":{}}',
    )

    assert responses[0]["id"] == ""
    assert responses[0]["error"]["code"] == ErrorCode.BAD_REQUEST
    assert responses[1]["ok"] is True


def test_the_client_calls_hello_and_ping(engine_executable):
    with BattleEngine(engine_executable) as engine:
        hello = engine.hello()
        assert engine.ping() == {}

    assert tuple(command["name"] for command in hello["commands"]) == DECLARED_COMMANDS


def test_the_client_raises_engine_error_on_a_refusal(engine_executable):
    with BattleEngine(engine_executable) as engine:
        with pytest.raises(EngineError) as refusal:
            engine.call("act", {})

        assert refusal.value.code == ErrorCode.NOT_IMPLEMENTED
        assert engine.ping() == {}


def test_a_killed_engine_surfaces_as_engine_dead(engine_executable):
    with BattleEngine(engine_executable, timeout_s=5.0) as engine:
        engine.ping()
        os.kill(engine.pid, signal.SIGKILL)

        with pytest.raises(EngineDead):
            engine.ping()


def test_a_silent_engine_raises_engine_timeout(tmp_path):
    mute = _script(tmp_path / "mute", "sys.stdin.readline()\ntime.sleep(30)")

    with BattleEngine(mute, timeout_s=0.5) as engine:
        with pytest.raises(EngineTimeout):
            engine.ping()
