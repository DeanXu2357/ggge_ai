"""The command mode: one battle through the commands of the engine.

The loop of the user ruling of 2026-08-27. It reads the pending units
from the engine, the menu of each unit from 'actions', the answer of
the struck unit from 'reactions', and lets 'act' settle the engagement.
The loop holds no rule of the battle: the engine refuses an illegal
pick, and the loop takes the refusal as the answer and tries the next
pick. A refused activation falls back to a standby, and the loop stops
on the field 'gone' of the answer of 'act'. The order of the picks is a
preference, not a rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .client import EngineError
from .contract import DiceMode


def decision(
    unit_id: str,
    kind: str,
    *,
    move_to: list[int] | None = None,
    target_id: str | None = None,
    weapon: str | None = None,
) -> dict[str, Any]:
    return {
        "unit_id": unit_id,
        "kind": kind,
        "move_to": move_to,
        "target_id": target_id,
        "weapon": weapon,
        "amount": None,
        "reaction": None,
        "support_defender": None,
        "support_attackers": [],
        "aim": None,
        "hit": None,
        "counter_hit": None,
        "support_hit": None,
    }


def reaction_of(option: dict[str, Any]) -> dict[str, Any]:
    return {
        "stance": option.get("stance"),
        "weapon": option.get("weapon"),
        "support_defender": None,
        "support_attackers": [],
    }


@dataclass
class Outcome:
    gone: list[str]
    turn: int
    log: list[dict[str, Any]] = field(default_factory=list)


class Player:
    def __init__(
        self,
        engine: Any,
        *,
        dice: dict[str, Any] | None = None,
        move_tries: int = 8,
    ) -> None:
        self._engine = engine
        self._dice = dice or {"mode": str(DiceMode.SAMPLED)}
        self._move_tries = move_tries

    def play(self, max_turns: int) -> Outcome:
        log: list[dict[str, Any]] = []
        gone: list[str] = []
        turn = 0
        while not gone:
            state = self._engine.call("export")["state"]
            turn = state["turn"]
            if turn > max_turns:
                break
            phase = state["phase"]
            living = [unit for unit in state["units"] if unit["hp"] > 0]
            pending = [unit for unit in living if unit["faction"] == phase and not unit["acted"]]
            if not pending:
                raise RuntimeError(f"the engine left the phase {phase!r} with no pending unit")
            actor = pending[0]
            foes = [unit for unit in living if unit["faction"] != phase]
            request, answer = self._settle(self._pick(actor, foes), actor)
            gone = answer["board"]["gone"]
            log.append(
                {
                    "turn": turn,
                    "phase": phase,
                    "actor_faction": actor["faction"],
                    "request": request,
                    "answer": answer,
                }
            )
        return Outcome(gone=gone, turn=turn, log=log)

    def _settle(
        self, request: dict[str, Any], actor: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            return request, self._engine.call("act", request)
        except EngineError:
            if request["action"]["kind"] == "standby":
                raise
            standby = self._standby(actor["unit_id"])
            return standby, self._engine.call("act", standby)

    def _pick(self, actor: dict[str, Any], foes: list[dict[str, Any]]) -> dict[str, Any]:
        menu = self._engine.call("actions", {"unit_id": actor["unit_id"]})
        ordered_foes = sorted(foes, key=lambda foe: _steps(actor["pos"], foe["pos"]))
        cells: list[list[int] | None] = [None]
        if ordered_foes:
            nearest = ordered_foes[0]["pos"]
            cells += sorted(menu.get("move_cells", []), key=lambda cell: _steps(cell, nearest))[
                : self._move_tries
            ]
        for cell in cells:
            for weapon in menu.get("weapons", []):
                if weapon.get("map_weapon") or (cell is not None and not weapon.get("usable_after_move")):
                    continue
                for foe in ordered_foes:
                    action = decision(
                        actor["unit_id"],
                        "attack",
                        move_to=cell,
                        target_id=foe["unit_id"],
                        weapon=weapon["name"],
                    )
                    try:
                        options = self._engine.call(
                            "reactions", {"action": action, "defender_id": foe["unit_id"]}
                        )
                    except EngineError:
                        continue
                    replies = options.get("defender", {}).get("reactions", [])
                    if not replies:
                        continue
                    return {
                        "unit_id": actor["unit_id"],
                        "action": action,
                        "reaction": reaction_of(replies[0]),
                        "dice": dict(self._dice),
                    }
        if len(cells) > 1 and cells[1] != actor["pos"]:
            return {
                "unit_id": actor["unit_id"],
                "action": decision(actor["unit_id"], "reposition", move_to=cells[1]),
                "dice": dict(self._dice),
            }
        return self._standby(actor["unit_id"])

    def _standby(self, unit_id: str) -> dict[str, Any]:
        return {
            "unit_id": unit_id,
            "action": decision(unit_id, "standby"),
            "dice": dict(self._dice),
        }


def _steps(a: list[int], b: list[int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])
