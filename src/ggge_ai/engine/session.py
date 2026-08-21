"""One battle, read through the engine.

The session holds the start state of a stage layout, sends it to the engine and
asks the engine every question. It holds no rule of the battle: a question that
needs one goes on the wire, and an engine that answers 'not_implemented' leaves
the answer empty.
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
from .state import DEFAULT_RULES, BattleState, EventTable, Rules

GONE = (EngineError, EngineDead, EngineTimeout)


class EngineSession:
    def __init__(
        self,
        engine: Any,
        state: BattleState,
        *,
        rules: Rules = DEFAULT_RULES,
        events: EventTable | None = None,
        stage: str = "",
    ) -> None:
        self._engine = engine
        self._state = state
        self._rules = rules
        self._events = events or {}
        self._stage = stage
        self._engine.call("load", {"state": self.engine_state(), "history": []})

    @classmethod
    def from_scenario(cls, path: str, engine: Any) -> EngineSession:
        text = Path(path).read_text(encoding="utf-8")
        loaded = scenario_mod.from_dict(json.loads(text))
        state, rules, events = loaded.build()
        return cls(engine, state, rules=rules, events=events, stage=loaded.stage)

    def engine_state(self) -> dict[str, Any]:
        return codec.encode_state(self._state)

    def snapshot(self) -> dict[str, Any]:
        return {
            "stage": self._stage,
            "turn": self._state.turn,
            "phase": str(self._state.phase),
            "bounds": self._state.bounds,
            "rules": codec.encode_rules(self._rules),
            "units": codec.encode_state(self._state)["units"],
        }

    def pending_decision(self) -> dict[str, Any]:
        units = []
        for unit in self._state.by_faction(Faction(self._state.phase)):
            if unit.acted:
                continue
            answer = self._ask("actions", {"unit_id": unit.unit_id})
            units.append({"unit_id": unit.unit_id, "candidates": answer.get("actions", [])})
        return {"turn": self._state.turn, "phase": str(self._state.phase), "units": units}

    def reaction_options(self, candidate: Mapping[str, Any]) -> dict[str, Any]:
        answer = self._ask("reactions", {"action": dict(candidate)})
        return {"options": answer.get("options", [])}

    def act(self, candidate: Mapping[str, Any], reaction: Mapping[str, Any] | None) -> dict:
        request: dict[str, Any] = {"action": dict(candidate)}
        if reaction is not None:
            request["reaction"] = dict(reaction)
        answer = self._ask("act", request)
        state = answer.get("state")
        if isinstance(state, dict):
            self._state = codec.decode_state(state)
        return self.snapshot()

    @staticmethod
    def candidate_key(candidate: Mapping[str, Any]) -> tuple:
        return tuple(sorted((key, str(value)) for key, value in candidate.items()))

    def _ask(self, cmd: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._engine.call(cmd, payload)
        except GONE:
            # The page must draw a board even when the engine answers nothing.
            return {}
