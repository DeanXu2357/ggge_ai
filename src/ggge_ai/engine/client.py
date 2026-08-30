"""Thin client of the battle engine process (spec: docs/spec/battle-engine-protocol.md)."""

from __future__ import annotations

import json
import os
import selectors
import subprocess
import time
from pathlib import Path
from types import TracebackType
from typing import Any

from .contract import PROTOCOL_VERSION

READ_CHUNK = 65536


class EngineError(RuntimeError):
    """An error response of the engine."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class EngineDead(RuntimeError):
    """The engine process is gone, or its stream is out of step."""


class EngineProtocolMismatch(EngineDead):
    """The engine speaks another version of the protocol."""


class EngineTimeout(RuntimeError):
    """The engine sent no answer inside the timeout."""


class BattleEngine:
    def __init__(self, executable: str | os.PathLike[str], timeout_s: float = 10.0) -> None:
        self._executable = str(Path(executable))
        self._timeout_s = timeout_s
        self._process: subprocess.Popen[bytes] | None = None
        self._selector: selectors.BaseSelector | None = None
        self._buffer = b""
        self._counter = 0

    @property
    def pid(self) -> int:
        if self._process is None:
            raise EngineDead("the engine is not running")
        return self._process.pid

    def start(self) -> None:
        if self._process is not None:
            return
        # A buffered stdin holds the request, and the engine waits for a line
        # that did not arrive.
        self._process = subprocess.Popen(
            [self._executable],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            bufsize=0,
        )
        self._selector = selectors.DefaultSelector()
        self._selector.register(self._process.stdout, selectors.EVENT_READ)
        self._buffer = b""

    def close(self) -> None:
        process, self._process = self._process, None
        selector, self._selector = self._selector, None
        if selector is not None:
            selector.close()
        if process is None:
            return
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        try:
            process.wait(timeout=self._timeout_s)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        if process.stdout is not None:
            process.stdout.close()

    def __enter__(self) -> BattleEngine:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def call(self, cmd: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._process is None:
            raise EngineDead("the engine is not running")
        self._counter += 1
        request_id = str(self._counter)
        self._write({"id": request_id, "cmd": cmd, "payload": payload or {}})
        response = json.loads(self._read_line(time.monotonic() + self._timeout_s))
        if response.get("id") != request_id:
            self.close()
            raise EngineDead(f"the answer carries the id {response.get('id')!r}")
        if not response.get("ok"):
            error = response.get("error") or {}
            raise EngineError(str(error.get("code", "")), str(error.get("message", "")))
        return response.get("payload") or {}

    def hello(self) -> dict[str, Any]:
        answer = self.call("hello")
        spoken = str(answer.get("protocol", ""))
        if spoken != PROTOCOL_VERSION:
            raise EngineProtocolMismatch(
                f"the engine speaks the protocol {spoken!r}, "
                f"and this client speaks {PROTOCOL_VERSION!r}"
            )
        return answer

    def ping(self) -> dict[str, Any]:
        return self.call("ping")

    def _write(self, request: dict[str, Any]) -> None:
        assert self._process is not None and self._process.stdin is not None
        line = json.dumps(request, separators=(",", ":")).encode("utf-8") + b"\n"
        try:
            self._process.stdin.write(line)
        except (BrokenPipeError, ValueError, OSError) as exc:
            raise EngineDead(f"the engine does not take the request: {exc}") from exc

    def _read_line(self, deadline: float) -> bytes:
        # A buffered readline cannot honor the timeout, so the client reads the
        # raw file descriptor and holds the remainder of the line.
        assert self._process is not None and self._process.stdout is not None
        fileno = self._process.stdout.fileno()
        while True:
            cut = self._buffer.find(b"\n")
            if cut >= 0:
                line, self._buffer = self._buffer[:cut], self._buffer[cut + 1 :]
                return line
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise EngineTimeout(f"the engine sent no answer in {self._timeout_s} s")
            assert self._selector is not None
            if not self._selector.select(remaining):
                continue
            try:
                chunk = os.read(fileno, READ_CHUNK)
            except OSError as exc:
                raise EngineDead(f"the engine stream is gone: {exc}") from exc
            if not chunk:
                raise EngineDead("the engine closed its output")
            self._buffer += chunk
