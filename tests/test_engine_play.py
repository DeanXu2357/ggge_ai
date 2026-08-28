"""The command mode against the built binary (user ruling 2026-08-27).

The loop reads every fact from the engine and holds no rule; the
engagement board of the frozen cases is the small battle, and the
placeholder scenario is the large one. The engagement board ends only
under forced hits: the accuracy values of the frozen fixtures and of the
placeholder scenario are placeholders that give a base hit rate under ten
percent, and a dodge takes it to zero.
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


def _play_engagement(engine_executable, seed: int, max_turns: int = 30, dice: dict | None = None):
    with BattleEngine(engine_executable) as engine:
        engine.call("load", {"state": _engagement_state(), "history": [], "seed": seed})
        return Player(engine, dice=dice).play(max_turns=max_turns)


def test_a_decision_carries_every_key_of_the_wire():
    assert decision("a", "standby") == {
        "unit_id": "a", "kind": "standby", "move_to": None, "target_id": None, "weapon": None,
        "amount": None, "response_attack": None, "support_defender": None, "support_attackers": [],
        "aim": None, "hit": None, "counter_hit": None, "support_hit": None,
    }


class _RefusesEveryPickButStandby:
    def __init__(self, gone: list[str], refuse_standby: bool = False) -> None:
        self.gone = gone
        self.refuse_standby = refuse_standby
        self.kinds: list[str] = []

    def call(self, cmd: str, payload: dict | None = None) -> dict:
        if cmd == "export":
            return {"state": {"turn": 1, "phase": "ally", "units": [
                {"unit_id": "a", "faction": "ally", "pos": [0, 0], "hp": 10, "acted": False},
                {"unit_id": "b", "faction": "enemy", "pos": [3, 0], "hp": 10, "acted": False},
            ]}}
        if cmd == "actions":
            return {"move_cells": [[1, 0]], "weapons": [
                {"name": "beam rifle", "usable_after_move": True},
                {"name": "saber", "usable_after_move": True},
            ]}
        if cmd == "response_attacks":
            return {"defender": {"response_attacks": [{"stance": "dodge", "weapon": None}]}}
        kind = payload["action"]["kind"]
        self.kinds.append(kind)
        if len(self.kinds) > 8:
            raise AssertionError("the loop did not stop on the field 'gone'")
        if kind != "standby" or self.refuse_standby:
            raise EngineError("illegal_action", "the engine refuses the pick")
        return {"events": [], "board": {"turn": 1, "phase": "ally", "pending": [], "gone": self.gone}}


def test_a_refused_pick_tries_the_next_candidate_and_then_the_standby():
    engine = _RefusesEveryPickButStandby(gone=["enemy"])

    outcome = Player(engine).play(max_turns=5)

    assert engine.kinds == ["attack"] * 4 + ["reposition", "standby"]
    assert outcome.gone == ["enemy"]
    assert [entry["request"]["action"]["kind"] for entry in outcome.log] == ["standby"]


def test_a_refused_standby_propagates():
    engine = _RefusesEveryPickButStandby(gone=[], refuse_standby=True)

    with pytest.raises(EngineError):
        Player(engine).play(max_turns=5)


def test_the_loop_plays_the_engagement_board_to_the_end(engine_executable):
    outcome = _play_engagement(engine_executable, seed=3, dice=FORCED_HITS)

    assert outcome.gone in (["ally"], ["enemy"], ["ally", "enemy"])
    assert {entry["phase"] for entry in outcome.log} >= {"ally", "enemy"}


def test_every_activation_is_of_the_side_of_its_phase(engine_executable):
    outcome = _play_engagement(engine_executable, seed=3)

    assert outcome.log
    for entry in outcome.log:
        assert entry["actor_faction"] == entry["phase"]


def test_an_attack_carries_the_response_attack_of_the_defender(engine_executable):
    outcome = _play_engagement(engine_executable, seed=3)

    attacks = [entry for entry in outcome.log if entry["request"]["action"]["kind"] == "attack"]
    assert attacks, "the engagement board holds foes in range"
    for entry in attacks:
        assert set(entry["request"]["response_attack"]) == {
            "stance", "weapon", "support_defender", "support_attackers",
        }
        assert entry["answer"]["events"][0]["event"] == "strike"


def test_the_sampled_battle_stalls_on_the_fixture_hit_rates(engine_executable):
    outcome = _play_engagement(engine_executable, seed=3, max_turns=5)

    events = [event for entry in outcome.log for event in entry["answer"]["events"]]
    strikes = [event for event in events if event["event"] == "strike"]
    assert strikes and not any(event["landed"] for event in strikes)


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
    assert outcome.turn >= 3 or outcome.gone
