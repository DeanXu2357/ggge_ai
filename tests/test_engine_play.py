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

from ggge_ai.engine.client import BattleEngine
from ggge_ai.engine.play import Player, decision
from ggge_ai.engine.session import EngineSession

ROOT = Path(__file__).resolve().parents[1]
ENGAGEMENT = ROOT / "tests/fixtures/engine/engagement_board.json"
PLACEHOLDER = ROOT / "assets/scenarios/uc_hard_1_placeholder.json"
FORCED_HITS = {"mode": "forced", "outcomes": ["hit", "hit", "hit", "hit"]}


def _engagement_state() -> dict:
    return json.loads(ENGAGEMENT.read_text(encoding="utf-8"))["setup"]["state"]


def _play_engagement(engine_executable, seed: int, max_turns: int = 30, dice: dict | None = None):
    with BattleEngine(engine_executable) as engine:
        engine.call("load", {"state": _engagement_state(), "history": [], "seed": seed})
        return Player(engine, dice=dice).play(max_turns=max_turns)


def test_a_decision_carries_every_key_of_the_wire():
    assert decision("a", "standby") == {
        "unit_id": "a", "kind": "standby", "move_to": None, "target_id": None, "weapon": None,
        "amount": None, "reaction": None, "support_defender": None, "support_attackers": [],
        "aim": None, "hit": None, "counter_hit": None, "support_hit": None,
    }


def test_the_loop_plays_the_engagement_board_to_the_end(engine_executable):
    outcome = _play_engagement(engine_executable, seed=3, dice=FORCED_HITS)

    assert outcome.gone in (["ally"], ["enemy"], ["ally", "enemy"])
    assert {entry["phase"] for entry in outcome.log} >= {"ally", "enemy"}


def test_every_activation_is_of_the_side_of_its_phase(engine_executable):
    outcome = _play_engagement(engine_executable, seed=3)

    for entry in outcome.log:
        assert entry["actor_faction"] == entry["phase"]


def test_an_attack_carries_the_reaction_of_the_defender(engine_executable):
    outcome = _play_engagement(engine_executable, seed=3)

    attacks = [entry for entry in outcome.log if entry["request"]["action"]["kind"] == "attack"]
    assert attacks, "the engagement board holds foes in range"
    for entry in attacks:
        assert set(entry["request"]["reaction"]) == {
            "stance", "weapon", "support_defender", "support_attackers",
        }
        assert entry["answer"]["events"][0]["event"] == "strike"


def test_the_sampled_battle_stalls_on_the_placeholder_hit_rates(engine_executable):
    outcome = _play_engagement(engine_executable, seed=3, max_turns=5)

    events = [event for entry in outcome.log for event in entry["answer"]["events"]]
    strikes = [event for event in events if event["event"] == "strike"]
    assert strikes and not any(event["landed"] for event in strikes)


def test_one_seed_gives_one_log(engine_executable):
    first = _play_engagement(engine_executable, seed=3)
    second = _play_engagement(engine_executable, seed=3)

    assert first.log == second.log


def test_the_placeholder_scenario_rotates_through_two_turns(engine_executable):
    with BattleEngine(engine_executable) as engine:
        EngineSession.from_scenario(str(PLACEHOLDER), engine, seed=5)
        outcome = Player(engine).play(max_turns=2)

    turns = [(entry["turn"], entry["phase"]) for entry in outcome.log]
    assert (1, "ally") in turns and (1, "enemy") in turns and (2, "ally") in turns
    assert outcome.turn >= 3 or outcome.gone
