"""One battle, read through the engine.

The session holds the state of one battle, sends it to the engine and asks the
engine every question. It speaks the commands of
'docs/spec/battle-engine-protocol.md' and nothing else. It holds no rule of the
battle: a question that needs one goes on the wire, and an engine that answers
'not_implemented' leaves the answer empty.

The engine answers 'act' with the events, the terminal values, the outcome
and a board summary, not with the new state, so the session reads the state
back with 'export'.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..stage import scenario as scenario_mod
from . import codec
from .client import EngineDead, EngineError, EngineTimeout
from .contract import Faction
from .state import BattleState, EventTable

GONE = (EngineError, EngineDead, EngineTimeout)


class EngineSession:
    def __init__(
        self,
        engine: Any,
        state: BattleState,
        *,
        events: EventTable | None = None,
        stage: str = "",
        seed: int = 0,
    ) -> None:
        self._engine = engine
        self._state = state
        self._events = events or {}
        self._stage = stage
        self._ask("load", {"state": self.engine_state(), "history": [], "seed": seed})

    @classmethod
    def from_scenario(cls, path: str, engine: Any, *, seed: int = 0) -> EngineSession:
        loaded = scenario_mod.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
        state, events = loaded.build()
        return cls(engine, state, events=events, stage=loaded.stage, seed=seed)

    def engine_state(self) -> dict[str, Any]:
        return codec.encode_state(self._state)

    def snapshot(self) -> dict[str, Any]:
        return {
            "stage": self._stage,
            "turn": self._state.turn,
            "phase": str(self._state.phase),
            "bounds": self._state.bounds,
            "units": self.engine_state()["units"],
        }

    def pending_decision(self) -> dict[str, Any]:
        phase = Faction(self._state.phase)
        units = []
        for unit_id, unit in enumerate(self._state.units):
            if unit.faction is not phase or unit.acted or not unit.alive:
                continue
            answer = self._ask("actions", {"unit_id": unit_id})
            units.append({"unit_id": unit_id, "actions": answer.get("actions", [])})
        return {"turn": self._state.turn, "phase": str(self._state.phase), "units": units}

    def response_attack_options(self, action: Mapping[str, Any]) -> dict[str, Any]:
        request = self._strike(action)
        if request is None:
            return {"response_attacks": []}
        answer = self._ask("response_attacks", request)
        return {"response_attacks": answer.get("response_attacks", [])}

    def act(
        self,
        candidate: Mapping[str, Any],
        response_attack: Mapping[str, Any] | None,
        stated: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        answer = self._ask("act", codec.encode_action(candidate, response_attack, stated))
        self._read_back()
        return {
            "events": answer.get("events", []),
            "units": answer.get("units", []),
            "outcome": answer.get("outcome", ""),
            "board": answer.get("board", {}),
        }

    def _strike(self, action: Mapping[str, Any]) -> dict[str, Any] | None:
        """The response attack request that one attack of the action list asks about.

        The command reads the cell of the attacker after its move, so a client
        can ask about a move that did not occur.
        """
        attacker = self._state.unit(action.get("unit_id"))
        if attacker is None or action.get("kind") != "attack" or action.get("target_id") is None:
            return None
        return {"defender_id": action.get("target_id"), "action": dict(action)}

    def _read_back(self) -> None:
        state = self._ask("export").get("state")
        if isinstance(state, dict):
            self._state = codec.decode_state(state)

    def _ask(self, cmd: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            return self._engine.call(cmd, payload or {})
        except GONE:
            # The page must draw a board even when the engine answers nothing.
            return {}
