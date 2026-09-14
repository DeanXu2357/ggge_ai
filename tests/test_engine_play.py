"""The command mode against the built binary (user ruling 2026-08-27).

The loop reads every fact from the engine and holds no rule; the
engagement board of the frozen cases is the small battle, and the
placeholder scenario is the large one. The engagement board ends only
under forced hits: the accuracy values of the frozen fixtures and of the
placeholder scenario are placeholders that give a base hit rate under ten
percent, so a drawn battle does not end in a few turns.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ggge_ai.engine.client import BattleEngine, EngineError
from ggge_ai.engine.play import FORCED_HITS, Player, decision
from ggge_ai.engine.session import EngineSession

ROOT = Path(__file__).resolve().parents[1]
ENGAGEMENT = ROOT / "tests/fixtures/engine/engagement_board.json"
PLACEHOLDER = ROOT / "assets/scenarios/uc_hard_1_placeholder.json"


def _engagement_state() -> dict:
    return json.loads(ENGAGEMENT.read_text(encoding="utf-8"))["setup"]["state"]


def _play_engagement(engine_executable, seed: int, max_turns: int = 30, stated: dict | None = None):
    with BattleEngine(engine_executable) as engine:
        engine.call("load", {"state": _engagement_state(), "history": [], "seed": seed})
        return Player(engine, stated=stated).play(max_turns=max_turns)


def _kind(request: dict) -> str:
    if "attack" in request:
        return "attack"
    if "move_to" in request:
        return "reposition"
    return "standby"


def test_a_decision_carries_every_key_of_the_wire():
    assert decision(0, "standby") == {
        "unit_id": 0,
        "kind": "standby",
        "move_to": None,
        "target_id": None,
        "weapon_id": None,
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


class _RefusesEveryPickButStandby:
    def __init__(self, outcome: str, refuse_standby: bool = False) -> None:
        self.outcome = outcome
        self.refuse_standby = refuse_standby
        self.kinds: list[str] = []

    def call(self, cmd: str, payload: dict | None = None) -> dict:
        if cmd == "export":
            return {
                "state": {
                    "turn": 1,
                    "phase": "ally",
                    "units": [
                        {"faction": "ally", "pos": [0, 0], "hp": 10, "acted": False},
                        {"faction": "enemy", "pos": [3, 0], "hp": 10, "acted": False},
                    ],
                }
            }
        if cmd == "actions":
            return {
                "move_cells": [[1, 0]],
                "weapons": [
                    {"name": "beam rifle", "usable_after_move": True},
                    {"name": "saber", "usable_after_move": True},
                ],
            }
        if cmd == "response_attacks":
            return {"defender": {"response_attacks": [{"stance": "dodge", "weapon_id": None}]}}
        kind = _kind(payload)
        self.kinds.append(kind)
        if len(self.kinds) > 8:
            raise AssertionError("the loop did not stop on the field 'outcome'")
        if kind != "standby" or self.refuse_standby:
            raise EngineError("illegal_action", "the engine refuses the pick")
        return {
            "events": [],
            "units": [],
            "outcome": self.outcome,
            "board": {"turn": 1, "phase": "ally", "pending_ids": [], "gone": []},
        }


def test_a_refused_pick_tries_the_next_candidate_and_then_the_standby():
    engine = _RefusesEveryPickButStandby(outcome="victory")

    played = Player(engine).play(max_turns=5)

    assert engine.kinds == ["attack"] * 4 + ["reposition", "standby"]
    assert played.outcome == "victory"
    assert [_kind(entry["request"]) for entry in played.log] == ["standby"]


def test_a_refused_standby_propagates():
    engine = _RefusesEveryPickButStandby(outcome="ongoing", refuse_standby=True)

    with pytest.raises(EngineError):
        Player(engine).play(max_turns=5)


def test_the_loop_plays_the_engagement_board_to_the_end(engine_executable):
    played = _play_engagement(engine_executable, seed=3, stated=FORCED_HITS)

    assert played.outcome in ("victory", "defeat")
    assert {entry["phase"] for entry in played.log} >= {"ally", "enemy"}


def test_every_activation_is_of_the_side_of_its_phase(engine_executable):
    outcome = _play_engagement(engine_executable, seed=3)

    assert outcome.log
    for entry in outcome.log:
        assert entry["actor_faction"] == entry["phase"]


def test_an_attack_carries_the_response_attack_of_the_defender(engine_executable):
    outcome = _play_engagement(engine_executable, seed=3)

    attacks = [entry for entry in outcome.log if _kind(entry["request"]) == "attack"]
    assert attacks, "the engagement board holds foes in range"
    for entry in attacks:
        assert set(entry["request"]["response_attack"]) == {
            "stance",
            "weapon_id",
            "support_defender_id",
            "support_attackers",
        }
        assert entry["answer"]["events"][0]["event"] == "strike"


def test_the_drawn_battle_stalls_on_the_fixture_hit_rates(engine_executable):
    played = _play_engagement(engine_executable, seed=3, max_turns=5)

    events = [event for entry in played.log for event in entry["answer"]["events"]]
    strikes = [event for event in events if event["event"] == "strike"]
    assert strikes and not all(event["landed"] for event in strikes)
    assert played.outcome == "ongoing"


def test_one_seed_gives_one_log(engine_executable):
    first = _play_engagement(engine_executable, seed=3)
    second = _play_engagement(engine_executable, seed=3)

    assert first.log
    assert first.log == second.log


def test_the_placeholder_scenario_rotates_through_two_turns(engine_executable):
    with BattleEngine(engine_executable) as engine:
        EngineSession.from_scenario(str(PLACEHOLDER), engine, seed=5)
        outcome = Player(engine).play(max_turns=2)

    turns = [(entry["turn"], entry["phase"]) for entry in outcome.log]
    assert (1, "ally") in turns and (1, "enemy") in turns and (2, "ally") in turns
    assert outcome.turn >= 3 or outcome.outcome != "ongoing"
