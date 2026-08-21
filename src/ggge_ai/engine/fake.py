"""A fake battle engine, inside the Python process.

The fake answers the shape of the contract and no rule of the battle. It exists
so that a caller can be wired and tested without the engine binary: the client
surface, the codec and the page all run against it, and every answer that needs
a rule of the battle is empty.

Do not read an answer of the fake as a fact of the game. A caller that wants a
rule asks the engine.
"""

from __future__ import annotations

from typing import Any

from .client import EngineError
from .contract import DECLARED_COMMANDS, PROTOCOL_VERSION, ErrorCode

IMPLEMENTED: tuple[str, ...] = (
    "hello",
    "ping",
    "load",
    "export",
    "reach",
    "actions",
    "reactions",
    "act",
)


class FakeEngine:
    """The client surface of 'BattleEngine', answered in this process."""

    def __init__(self) -> None:
        self._state: dict[str, Any] | None = None

    def start(self) -> None:
        return

    def close(self) -> None:
        self._state = None

    def __enter__(self) -> FakeEngine:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def hello(self) -> dict[str, Any]:
        return self.call("hello")

    def ping(self) -> dict[str, Any]:
        return self.call("ping")

    def call(self, cmd: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        if cmd not in DECLARED_COMMANDS:
            raise EngineError(ErrorCode.UNKNOWN_COMMAND, f"the contract declares no {cmd!r}")
        if cmd not in IMPLEMENTED:
            raise EngineError(ErrorCode.NOT_IMPLEMENTED, f"the fake answers no {cmd!r}")
        return getattr(self, f"_{cmd}")(payload)

    def _hello(self, _: dict[str, Any]) -> dict[str, Any]:
        commands = [
            {"name": name, "implemented": name in IMPLEMENTED} for name in DECLARED_COMMANDS
        ]
        return {"protocol": PROTOCOL_VERSION, "commands": commands, "engine": "fake"}

    def _ping(self, _: dict[str, Any]) -> dict[str, Any]:
        return {}

    def _load(self, payload: dict[str, Any]) -> dict[str, Any]:
        state = payload.get("state")
        if not isinstance(state, dict):
            raise EngineError(ErrorCode.BAD_REQUEST, "the load carries no state")
        self._state = state
        return {"units": len(state.get("units", []))}

    def _reach(self, payload: dict[str, Any]) -> dict[str, Any]:
        unit = self._unit(payload.get("unit_id"))
        return {"cells": [unit.get("pos")]}

    def _actions(self, payload: dict[str, Any]) -> dict[str, Any]:
        unit = self._unit(payload.get("unit_id"))
        return {"actions": [{"unit_id": unit.get("unit_id"), "kind": "standby"}]}

    def _reactions(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._unit(payload.get("defender_id"))
        self._unit(payload.get("attacker_id"))
        return {"reactions": []}

    def _act(self, payload: dict[str, Any]) -> dict[str, Any]:
        # The fake runs no action: it marks the unit and leaves the board.
        unit = self._unit(payload.get("unit_id"))
        unit["acted"] = True
        return {"events": [], "board": self._summary()}

    def _export(self, _: dict[str, Any]) -> dict[str, Any]:
        return {"state": self._loaded(), "history": []}

    def _summary(self) -> dict[str, Any]:
        # The shape of the board summary, with no unit in the pending list: who
        # waits is a rule of the battle, and the fake holds none.
        state = self._loaded()
        return {"turn": state.get("turn"), "phase": state.get("phase"), "pending": []}

    def _loaded(self) -> dict[str, Any]:
        if self._state is None:
            raise EngineError(ErrorCode.NO_SESSION, "the fake holds no board")
        return self._state

    def _unit(self, unit_id: Any) -> dict[str, Any]:
        for unit in self._loaded().get("units", []):
            if unit.get("unit_id") == unit_id:
                return unit
        raise EngineError(ErrorCode.ILLEGAL_ACTION, f"the board holds no unit {unit_id!r}")
