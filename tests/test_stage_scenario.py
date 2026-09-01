"""情境檔載入器：佔位關卡的組裝結果、格式錯誤的把關、勝敗判定與 spawn 參照。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ggge_ai.stage import scenario as scenario_mod
from ggge_ai.engine.contract import Faction, Terrain
from ggge_ai.engine.state import StageEvent

PLACEHOLDER = Path(__file__).resolve().parents[1] / "assets/scenarios/uc_hard_1_placeholder.json"


@pytest.fixture
def placeholder() -> dict:
    return json.loads(PLACEHOLDER.read_text(encoding="utf-8"))


def test_placeholder_scenario_builds_the_turn_one_board():
    scenario = scenario_mod.load(PLACEHOLDER)
    state, events = scenario.build()

    assert len(state.enemies()) == 18
    assert len(state.allies()) == 10
    assert state.turn == 1
    assert state.phase is Faction.ALLY
    assert state.bounds == ((0, 0), (24, 19))
    assert events == {}


def test_placeholder_enemy_matches_the_verified_truth_row():
    scenario = scenario_mod.load(PLACEHOLDER)
    state, _events = scenario.build()

    unit = state.units[0]

    assert unit.pos == (9, 4)
    assert (unit.hp, unit.max_hp) == (83811, 83811)
    assert (unit.en, unit.en_max) == (513, 513)
    assert unit.faction is Faction.ENEMY


def test_placeholder_allies_stand_on_the_recorded_sortie_cells():
    scenario = scenario_mod.load(PLACEHOLDER)
    state, _events = scenario.build()

    cells = {u.pos for u in state.allies()}

    assert (2, 6) in cells
    assert (17, 9) in cells


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
    state, events = scenario.build()

    event = events["wave2"]
    assert isinstance(event, StageEvent)
    assert state.pending_events == ("wave2",)
    (template,) = event.effect["units"]
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


def test_support_placeholder_carries_a_skill_and_a_shield():
    scenario = scenario_mod.load(PLACEHOLDER)
    state, _events = scenario.build()

    support = next(u for u in state.allies() if u.has_shield)

    assert [s.kind for s in support.skills] == ["skill_en_refill"]


def test_the_board_carries_the_terrain_of_the_map(placeholder):
    placeholder["board"]["terrain"] = "ground"
    placeholder["board"]["terrain_cells"] = [{"cell": [3, 2], "terrain": "underwater"}]

    scenario = scenario_mod.from_dict(placeholder)
    state, _ = scenario.build()

    assert scenario.board.terrain is Terrain.GROUND
    assert state.terrain is Terrain.GROUND
    assert state.terrain_cells[0].cell == (3, 2)
    assert state.terrain_cells[0].terrain is Terrain.UNDERWATER


def test_a_board_with_no_terrain_names_none(placeholder):
    scenario = scenario_mod.from_dict(placeholder)
    state, _ = scenario.build()

    assert scenario.board.terrain is None
    assert state.terrain is None
    assert state.terrain_cells == ()


def test_the_board_refuses_a_terrain_outside_the_contract(placeholder):
    placeholder["board"]["terrain"] = "orbit"

    with pytest.raises(ValueError, match="地形不在合約內"):
        scenario_mod.from_dict(placeholder)


def test_the_board_refuses_a_terrain_cell_off_the_board(placeholder):
    placeholder["board"]["terrain_cells"] = [{"cell": [999, 0], "terrain": "ground"}]

    with pytest.raises(ValueError, match="地形格出界"):
        scenario_mod.from_dict(placeholder)


def test_the_board_refuses_one_cell_two_times(placeholder):
    placeholder["board"]["terrain_cells"] = [
        {"cell": [1, 1], "terrain": "ground"},
        {"cell": [1, 1], "terrain": "surface"},
    ]

    with pytest.raises(ValueError, match="地形格重複"):
        scenario_mod.from_dict(placeholder)
