from __future__ import annotations

import json
from pathlib import Path

from ggge_ai_2.uisim.contract import RatioRect, UiScreen
from ggge_ai_2.uisim.stages import ButtonDef, CallerGroup, ScreenDef, load_stages

REAL_STAGES = Path(__file__).resolve().parents[4] / "assets" / "ui_stages" / "stages.json"

SMALL_STAGES = {
    "gesture_description": "ignored",
    "reserved": [{"name": "undefined", "zh": "未定義", "description": "ignored"}],
    "screens": [
        {
            "name": "battle_prep_attack",
            "zh": "攻擊準備",
            "kind": "page",
            "control": "player",
            "description": "ignored",
            "buttons": [
                {
                    "name": "battle_prep_attack__detail",
                    "zh": "詳情",
                    "description": "ignored",
                    "to": ["battle_prep_detail@battle_prep_attack"],
                    "rect": [0.1, 0.2, 0.3, 0.4],
                    "deadline": 15.0,
                },
                {
                    "name": "battle_prep_attack__buy",
                    "zh": "購買",
                    "description": "ignored",
                    "to": [],
                    "forbidden": True,
                    "deadline": 10.0,
                },
            ],
        },
        {
            "name": "non_player_phase_battle_view",
            "zh": "敵軍回合",
            "kind": "map_mode.non_player_phase",
            "control": "game",
            "description": "ignored",
            "buttons": [],
            "game_to": ["player_phase_overview"],
        },
    ],
    "caller_groups": {
        "battle_prep_detail": {
            "zh": "戰鬥準備詳情",
            "entry": ["battle_prep_detail"],
            "inside": ["battle_info_preview"],
            "note": "ignored",
        }
    },
}


def test_small_file_is_parsed_into_definitions(tmp_path: Path):
    path = tmp_path / "stages.json"
    path.write_text(json.dumps(SMALL_STAGES), encoding="utf-8")

    stages = load_stages(path)

    assert stages.screens["battle_prep_attack"] == ScreenDef(
        name="battle_prep_attack",
        kind="page",
        control="player",
        buttons=(
            ButtonDef(
                name="battle_prep_attack__detail",
                to=("battle_prep_detail@battle_prep_attack",),
                rect=RatioRect(0.1, 0.2, 0.3, 0.4),
                gesture=None,
                dynamic=False,
                forbidden=False,
                deadline=15.0,
            ),
            ButtonDef(
                name="battle_prep_attack__buy",
                to=(),
                rect=None,
                gesture=None,
                dynamic=False,
                forbidden=True,
                deadline=10.0,
            ),
        ),
        game_to=(),
    )
    assert stages.screens["non_player_phase_battle_view"] == ScreenDef(
        name="non_player_phase_battle_view",
        kind="map_mode.non_player_phase",
        control="game",
        buttons=(),
        game_to=("player_phase_overview",),
    )
    assert stages.groups == {
        "battle_prep_detail": CallerGroup(
            name="battle_prep_detail",
            entry=("battle_prep_detail",),
            inside=("battle_info_preview",),
        )
    }


def test_real_file_defines_every_ui_screen():
    stages = load_stages(REAL_STAGES)

    assert {screen.value for screen in UiScreen} <= stages.screens.keys()
