"""The command mode: one battle through the commands of the engine.

The loop of the user ruling of 2026-08-27. It reads the pending units
from the engine, the menu of each unit from 'actions', the answer of
the struck unit from 'response_attacks', and lets 'act' settle the
engagement.
The loop holds no rule of the battle: the engine refuses an illegal
candidate, and the loop takes the refusal as the answer and tries the
next candidate. A standby closes the list, and the loop stops when the
field 'outcome' of the answer of 'act' leaves 'ongoing'. The order of
the candidates is a preference, not a rule; '_steps' gives that order
and is not the distance of the board, which the engine alone holds.
The loop plays both sides, and for the defender it prefers the stance
'none': the unit stands, so a stated hit stays a behavior the rates
give a chance of.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from . import codec
from .client import EngineError

FORCED_HITS = {"crit": False, "hit": True}


def decision(
    unit_id: int,
    kind: str,
    *,
    move_to: list[int] | None = None,
    target_id: int | None = None,
    weapon_id: int | None = None,
) -> dict[str, Any]:
    return {
        "unit_id": unit_id,
        "kind": kind,
        "move_to": move_to,
        "target_id": target_id,
        "weapon_id": weapon_id,
        "map_weapon_id": None,
        "amount": None,
        "response_attack": None,
        "support_defender_id": None,
        "support_attacker_ids": [],
        "aim": None,
        "hit": None,
        "counter_hit": None,
        "support_hit": None,
    }


def response_attack_of(option: dict[str, Any]) -> dict[str, Any]:
    return {
        "stance": option.get("stance"),
        "weapon_id": option.get("weapon_id"),
        "support_defender_id": None,
        "support_attackers": [],
    }


def standing(replies: list[dict[str, Any]]) -> dict[str, Any]:
    for option in replies:
        if option.get("stance") == "none":
            return option
    return replies[0]


@dataclass
class Played:
    outcome: str
    turn: int
    log: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class Standing:
    """One unit of the board, with the position that names it."""

    unit_id: int
    unit: dict[str, Any]


class Player:
    def __init__(
        self,
        engine: Any,
        *,
        stated: dict[str, Any] | None = None,
        move_tries: int = 8,
    ) -> None:
        self._engine = engine
        self._stated = stated
        self._move_tries = move_tries

    def play(self, max_turns: int) -> Played:
        log: list[dict[str, Any]] = []
        outcome = "ongoing"
        turn = 0
        while outcome == "ongoing":
            state = self._engine.call("export")["state"]
            turn = state["turn"]
            if turn > max_turns:
                break
            phase = state["phase"]
            living = [
                Standing(unit_id=index, unit=unit)
                for index, unit in enumerate(state["units"])
                if unit["hp"] > 0
            ]
            pending = [
                one for one in living if one.unit["faction"] == phase and not one.unit["acted"]
            ]
            if not pending:
                raise RuntimeError(f"the engine left the phase {phase!r} with no pending unit")
            actor = pending[0]
            foes = [one for one in living if one.unit["faction"] != phase]
            request, answer = self._settle(actor, foes)
            outcome = answer["outcome"]
            log.append(
                {
                    "turn": turn,
                    "phase": phase,
                    "actor_faction": actor.unit["faction"],
                    "request": request,
                    "answer": answer,
                }
            )
        return Played(outcome=outcome, turn=turn, log=log)

    def _settle(
        self, actor: Standing, foes: list[Standing]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        for request in self._candidates(actor, foes):
            try:
                return request, self._engine.call("act", request)
            except EngineError:
                continue
        standby = self._standby(actor.unit_id)
        return standby, self._engine.call("act", standby)

    def _candidates(self, actor: Standing, foes: list[Standing]) -> Iterator[dict[str, Any]]:
        menu = self._engine.call("actions", {"unit_id": actor.unit_id})
        ordered_foes = sorted(foes, key=lambda foe: _steps(actor.unit["pos"], foe.unit["pos"]))
        cells: list[list[int] | None] = [None]
        if ordered_foes:
            nearest = ordered_foes[0].unit["pos"]
            cells += sorted(menu.get("move_cells", []), key=lambda cell: _steps(cell, nearest))[
                : self._move_tries
            ]
        for cell in cells:
            for weapon_id, weapon in enumerate(menu.get("weapons", [])):
                if cell is not None and not weapon.get("usable_after_move"):
                    continue
                for foe in ordered_foes:
                    action = decision(
                        actor.unit_id,
                        "attack",
                        move_to=cell,
                        target_id=foe.unit_id,
                        weapon_id=weapon_id,
                    )
                    try:
                        options = self._engine.call(
                            "response_attacks", {"action": action, "defender_id": foe.unit_id}
                        )
                    except EngineError:
                        continue
                    replies = options.get("defender", {}).get("response_attacks", [])
                    if not replies:
                        continue
                    yield codec.encode_action(
                        action, response_attack_of(standing(replies)), self._stated
                    )
        if len(cells) > 1 and cells[1] != actor.unit["pos"]:
            yield codec.encode_action(decision(actor.unit_id, "reposition", move_to=cells[1]))

    def _standby(self, unit_id: int) -> dict[str, Any]:
        return codec.encode_action(decision(unit_id, "standby"))


def _steps(a: list[int], b: list[int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])
