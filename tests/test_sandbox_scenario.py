"""情境檔載入器：佔位關卡的組裝結果、格式錯誤的把關、勝敗判定與 spawn 參照。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ggge_ai.sandbox import scenario as scenario_mod
from ggge_ai.sandbox.model import Faction, MoveKind, StageEvent

PLACEHOLDER = Path(__file__).resolve().parents[1] / "assets/scenarios/uc_hard_1_placeholder.json"


@pytest.fixture
def placeholder() -> dict:
    return json.loads(PLACEHOLDER.read_text(encoding="utf-8"))


def test_placeholder_scenario_builds_the_turn_one_board():
    scenario = scenario_mod.load(PLACEHOLDER)
    state, rules, events = scenario.build()

    assert len(state.enemies()) == 18
    assert len(state.allies()) == 4
    assert state.turn == 1
    assert state.phase is Faction.ALLY
    assert state.bounds == ((0, 0), (24, 19))
    assert rules == scenario_mod.DEFAULT_RULES
    assert events == {}


def test_placeholder_enemy_matches_the_verified_truth_row():
    scenario = scenario_mod.load(PLACEHOLDER)
    state, _rules, _events = scenario.build()

    unit = next(u for u in state.units if u.pos == (9, 4))

    assert (unit.hp, unit.max_hp) == (83811, 83811)
    assert (unit.en, unit.en_max) == (513, 513)
    assert unit.unit_id == "e1"
    assert unit.faction is Faction.ENEMY


def test_unknown_format_is_rejected(placeholder):
    placeholder["format"] = "sandbox-scenario/9"

    with pytest.raises(ValueError, match="格式不符"):
        scenario_mod.from_dict(placeholder)


def test_unknown_intel_id_is_rejected(placeholder):
    placeholder["deployment"][0]["intel_id"] = "nope"

    with pytest.raises(ValueError, match="查無此筆"):
        scenario_mod.from_dict(placeholder)


def test_out_of_bounds_cell_is_rejected(placeholder):
    placeholder["deployment"][0]["cell"] = [25, 4]

    with pytest.raises(ValueError, match="越界"):
        scenario_mod.from_dict(placeholder)


def test_duplicate_uid_is_rejected(placeholder):
    placeholder["deployment"][1]["uid"] = placeholder["deployment"][0]["uid"]

    with pytest.raises(ValueError, match="uid 重複"):
        scenario_mod.from_dict(placeholder)


def test_outcome_is_open_then_victory_then_defeat():
    scenario = scenario_mod.load(PLACEHOLDER)
    state, _rules, _events = scenario.build()
    assert scenario_mod.check_outcome(scenario, state) is None

    cleared = state.clone()
    cleared.units = [u for u in cleared.units if u.faction is not Faction.ENEMY]
    assert scenario_mod.check_outcome(scenario, cleared) == "victory"

    wiped = state.clone()
    wiped.units = [u for u in wiped.units if u.faction is not Faction.ALLY]
    assert scenario_mod.check_outcome(scenario, wiped) == "defeat"


def test_destroy_target_and_protect_conditions(placeholder):
    placeholder["victory"] = {"type": "destroy_target", "uid": "e1"}
    placeholder["defeat"] = {"type": "protect", "uid": "a1"}
    scenario = scenario_mod.from_dict(placeholder)
    state, _rules, _events = scenario.build()
    assert scenario_mod.check_outcome(scenario, state) is None

    killed = state.clone()
    killed.units = [u for u in killed.units if u.unit_id != "e1"]
    assert scenario_mod.check_outcome(scenario, killed) == "victory"

    lost = state.clone()
    lost.units = [u for u in lost.units if u.unit_id != "a1"]
    assert scenario_mod.check_outcome(scenario, lost) == "defeat"


def test_spawn_effect_units_are_assembled_from_intel_references(placeholder):
    placeholder["events"] = {
        "wave2": {
            "trigger": {"type": "turn_start", "turn": 3},
            "effect": {
                "type": "spawn",
                "units": [
                    {
                        "uid": "e19",
                        "intel_id": "enemy_placeholder_t1",
                        "faction": "enemy",
                        "cell": [12, 2],
                    }
                ],
            },
        }
    }
    scenario = scenario_mod.from_dict(placeholder)
    state, _rules, events = scenario.build()

    event = events["wave2"]
    assert isinstance(event, StageEvent)
    assert state.pending_events == ("wave2",)
    (template,) = event.effect["units"]
    assert template.unit_id == "e19"
    assert template.faction is Faction.ENEMY
    assert template.pos == (12, 2)
    assert template.hp == template.max_hp == 29265


def test_spawn_reference_shares_the_uid_namespace(placeholder):
    placeholder["events"] = {
        "wave2": {
            "trigger": {"type": "turn_start", "turn": 3},
            "effect": {
                "type": "spawn",
                "units": [
                    {
                        "uid": "e1",
                        "intel_id": "enemy_placeholder_t1",
                        "faction": "enemy",
                        "cell": [12, 2],
                    }
                ],
            },
        }
    }

    with pytest.raises(ValueError, match="uid 重複"):
        scenario_mod.from_dict(placeholder)


def test_rules_overrides_replace_only_named_fields(placeholder):
    placeholder["rules"] = {"terrain": 1.25}
    scenario = scenario_mod.from_dict(placeholder)

    assert scenario.rules.terrain == 1.25
    assert scenario.rules.defend_multiplier == scenario_mod.DEFAULT_RULES.defend_multiplier

    placeholder["rules"] = {"nope": 1}
    with pytest.raises(ValueError, match="未知欄位"):
        scenario_mod.from_dict(placeholder)


def test_support_placeholder_carries_a_skill_and_a_shield():
    scenario = scenario_mod.load(PLACEHOLDER)
    state, _rules, _events = scenario.build()

    support = next(u for u in state.allies() if u.has_shield)

    assert [s.kind for s in support.skills] == [MoveKind.SKILL_EN_REFILL]
