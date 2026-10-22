from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from ggge_ai_2.interpreter.contract import Screen

_POWER_SAVE = frozenset({Screen.POWER_SAVE_LOCK, Screen.POWER_SAVE_DIM})
_PASS_THROUGH_FROM_STAGES = (
    Screen.LOADING,
    Screen.SIMPLIFY_WEAPON_ANIME,
    Screen.EX_WEAPON_ANIME,
    Screen.BATTLE_CLEAR_VIEW,
)
_PASS_THROUGH = frozenset({*_PASS_THROUGH_FROM_STAGES, Screen.MAP_PASSING})
GAME_SCREENS = tuple(s for s in Screen if s not in _POWER_SAVE and s not in _PASS_THROUGH)

_MAP_PASSING_LINE = (
    "The battle map, but the top-left turn box ('TURN' with a number and '破壞數') is missing,"
    " or an attack animation plays over the map. Use this only when no battle screen above fits."
)

_TASK = (
    "You see one screenshot of the mobile game 'SD Gundam G Generation ETERNAL'"
    " (landscape 2340x1080, downscaled). Name the screen."
    " Answer only with the JSON the request asks for."
)

_BATTLE_TITLE_RULES = (
    "On the battle map, read the title at the top left first."
    " '敵軍回合', '隱藏軍回合' or '第三軍回合' means non_player_phase_battle_view."
    " '我軍回合' means player_phase_overview. '單位移動' means select_action_in_battle."
    " '選擇武裝' means select_weapon_in_battle.",
    "'戰鬥準備 -攻擊-' with an orange '開始戰鬥' button at the bottom right means"
    " battle_prep_attack; with a blue '行動選擇' button it means select_weapon_in_battle.",
    "'戰鬥準備 -應戰-' with an orange '開始戰鬥' button means battle_prep_response_attack.",
)

_AUTO_RULE = (
    "Report auto as true or false only when the screen has the AUTO button at the top right;"
    " otherwise report null. During the enemy turn the AUTO button can look lit;"
    " that is not auto mode."
)

_ANSWER_RULES = (
    "screen is one of the screen values above, one of the pass-through values, or 'unknown'"
    " when no entry fits. Do not pick the closest screen when none fits; answer 'unknown'."
    " The request lists the candidate screens the program expects; they are hints, not limits."
)


def system_prompt(stages: Mapping[str, object]) -> str:
    entries = _screen_entries(stages)
    lines = ["# Task", _TASK, "", "# Screens"]
    lines += [f"- {s.value} ({entries[s][0]}): {entries[s][1]}" for s in GAME_SCREENS]
    lines += ["", "# Pass-through screens"]
    lines += [f"- {s.value}: {entries[s][1]}" for s in _PASS_THROUGH_FROM_STAGES]
    lines += [f"- {Screen.MAP_PASSING.value}: {_MAP_PASSING_LINE}"]
    lines += ["", "# Battle title rules"]
    lines += [f"- {rule}" for rule in _BATTLE_TITLE_RULES]
    lines += ["", "# AUTO", str(stages["auto_mode_description"]), _AUTO_RULE]
    lines += ["", "# Answer rules", _ANSWER_RULES]
    return "\n".join(lines) + "\n"


def _screen_entries(stages: Mapping[str, object]) -> dict[Screen, tuple[str, str]]:
    raw_screens = cast(list[Mapping[str, object]], stages["screens"])
    by_name = {str(raw["name"]): raw for raw in raw_screens}
    return {
        screen: (str(by_name[screen.value]["zh"]), str(by_name[screen.value]["description"]))
        for screen in (*GAME_SCREENS, *_PASS_THROUGH_FROM_STAGES)
    }
