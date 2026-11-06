from __future__ import annotations

from ggge_ai_2.uisim.chart import (
    AutoButton,
    Chart,
    Group,
    ScreenChart,
    Target,
    Transition,
    UiElement,
)
from ggge_ai_2.uisim.contract import RatioRect, UiScreen

CHART = Chart(
    screens={
        UiScreen.STAGE_CHOSEN: ScreenChart(
            transitions=(
                Transition(
                    "stage_chosen__ap_bar",
                    RatioRect(0.645, 0.015, 0.73, 0.085),
                    (Target(UiScreen.AP_RECOVERY_OVERLAY, "ap_recovery"),),
                    3.0,
                ),
                Transition(
                    "stage_chosen__main_stage",
                    RatioRect(0.153, 0.618, 0.471, 0.824),
                    (Target(UiScreen.SERIES_LIST),),
                    6.1,
                ),
                Transition(
                    "stage_chosen__event",
                    RatioRect(0.494, 0.163, 0.691, 0.655),
                    (Target(UiScreen.EVENT_STAGE_LIST),),
                    4.6,
                ),
                Transition(
                    "stage_chosen__upgrade_stages",
                    RatioRect(0.511, 0.693, 0.699, 0.88),
                    (Target(UiScreen.TRAINING_STAGE_LIST),),
                    3.0,
                ),
            )
        ),
        UiScreen.SERIES_LIST: ScreenChart(
            transitions=(
                Transition(
                    "series_list__series",
                    RatioRect(0.338, 0.357, 0.525, 0.65),
                    (Target(UiScreen.SERIES_STAGE_INFO),),
                    12.2,
                ),
            )
        ),
        UiScreen.SERIES_STAGE_INFO: ScreenChart(
            transitions=(
                Transition(
                    "series_stage_info__back",
                    RatioRect(0.075, 0.016, 0.143, 0.081),
                    (Target(UiScreen.SERIES_LIST),),
                    3.0,
                ),
                Transition(
                    "series_stage_info__select",
                    RatioRect(0.77, 0.769, 0.925, 0.878),
                    (Target(UiScreen.STORY_STAGE_LIST),),
                    4.7,
                ),
            )
        ),
        UiScreen.STORY_STAGE_LIST: ScreenChart(
            transitions=(
                Transition(
                    "story_stage_list__back",
                    RatioRect(0.075, 0.016, 0.143, 0.076),
                    (Target(UiScreen.SERIES_LIST),),
                    3.0,
                ),
                Transition(
                    "story_stage_list__skip",
                    RatioRect(0.795, 0.6, 0.905, 0.71),
                    (Target(UiScreen.SKIP_STAGE_OVERLAY),),
                    9.2,
                ),
                Transition(
                    "story_stage_list__sortie_prepare",
                    RatioRect(0.773, 0.775, 0.925, 0.878),
                    (Target(UiScreen.SORTIE_PREP),),
                    6.1,
                ),
            )
        ),
        UiScreen.ETERNAL_STAGE_LIST: ScreenChart(
            transitions=(
                Transition(
                    "eternal_stage_list__back",
                    RatioRect(0.075, 0.016, 0.143, 0.081),
                    (Target(UiScreen.STAGE_CHOSEN),),
                    3.0,
                ),
                Transition(
                    "eternal_stage_list__sortie_target",
                    RatioRect(0.756, 0.674, 0.865, 0.74),
                    (Target(UiScreen.STAGE_ALLOW_LIST),),
                    3.1,
                ),
                Transition(
                    "eternal_stage_list__sortie_prepare",
                    RatioRect(0.733, 0.772, 0.886, 0.88),
                    (Target(UiScreen.SORTIE_PREP),),
                    6.0,
                ),
            )
        ),
        UiScreen.EVENT_STAGE_LIST: ScreenChart(),
        UiScreen.SKIP_STAGE_OVERLAY: ScreenChart(
            transitions=(
                Transition(
                    "skip_stage_overlay__execute",
                    RatioRect(0.509, 0.735, 0.661, 0.84),
                    (Target(UiScreen.STORY_STAGE_LIST),),
                    7.6,
                ),
            )
        ),
        UiScreen.SKIP_RESULT_LIST: ScreenChart(
            transitions=(
                Transition(
                    "skip_result_list__ok",
                    RatioRect(0.735, 0.861, 0.885, 0.964),
                    (
                        Target(UiScreen.SKIP_STAGE_OVERLAY),
                        Target(UiScreen.STORY_STAGE_LIST),
                        Target(UiScreen.TRAINING_STAGE_LIST),
                    ),
                    3.0,
                ),
                Transition(
                    "skip_result_list__reward_item",
                    RatioRect(0.13, 0.185, 0.195, 0.33),
                    (Target(UiScreen.REWARD_DETAIL),),
                    3.0,
                ),
            )
        ),
        UiScreen.SORTIE_PREP: ScreenChart(
            transitions=(
                Transition(
                    "sortie_prep__back",
                    RatioRect(0.075, 0.016, 0.143, 0.081),
                    (Target(UiScreen.ETERNAL_STAGE_LIST),),
                    3.1,
                ),
                Transition(
                    "sortie_prep__edit_all",
                    RatioRect(0.469, 0.905, 0.578, 0.97),
                    (Target(UiScreen.ROSTER_ALL_EDIT),),
                    4.6,
                ),
                Transition(
                    "sortie_prep__sortie",
                    RatioRect(0.733, 0.861, 0.888, 0.97),
                    (Target(UiScreen.BATTLE_INFO_PREVIEW),),
                    15.0,
                ),
            )
        ),
        UiScreen.ROSTER_ALL_EDIT: ScreenChart(
            transitions=(
                Transition(
                    "roster_all_edit__replace",
                    RatioRect(0.508, 0.865, 0.66, 0.965),
                    (Target(UiScreen.SORTIE_PREP),),
                    6.1,
                ),
            )
        ),
        UiScreen.TRAINING_STAGE_LIST: ScreenChart(
            transitions=(
                Transition(
                    "training_stage_list__back",
                    RatioRect(0.075, 0.016, 0.143, 0.081),
                    (Target(UiScreen.STAGE_CHOSEN),),
                    3.1,
                ),
                Transition(
                    "training_stage_list__batch_skip",
                    RatioRect(0.668, 0.807, 0.822, 0.875),
                    (Target(UiScreen.BATCH_SKIP_OVERLAY),),
                    3.1,
                ),
            )
        ),
        UiScreen.BATCH_SKIP_OVERLAY: ScreenChart(
            transitions=(
                Transition(
                    "batch_skip_overlay__execute",
                    RatioRect(0.508, 0.867, 0.663, 0.972),
                    (Target(UiScreen.SKIP_RESULT_LIST),),
                    7.7,
                ),
            )
        ),
        UiScreen.AP_RECOVERY_OVERLAY: ScreenChart(
            transitions=(
                Transition(
                    "ap_recovery_overlay__ap_pack",
                    RatioRect(0.309, 0.303, 0.703, 0.504),
                    (Target(UiScreen.AP_RECOVERY_ITEM_CHECK),),
                    15.0,
                ),
                Transition(
                    "ap_recovery_overlay__close",
                    RatioRect(0.428, 0.867, 0.581, 0.972),
                    (Target(UiScreen.STAGE_CHOSEN),),
                    15.0,
                ),
                Transition(
                    "ap_recovery_overlay__outside", None, (Target(UiScreen.STAGE_CHOSEN),), 15.0
                ),
            ),
            danger=(RatioRect(0.309, 0.529, 0.703, 0.802),),
        ),
        UiScreen.AP_RECOVERY_ITEM_CHECK: ScreenChart(
            transitions=(
                Transition(
                    "ap_recovery_item_check__cancel",
                    RatioRect(0.349, 0.733, 0.5, 0.84),
                    (Target(UiScreen.STAGE_CHOSEN),),
                    15.0,
                ),
                Transition(
                    "ap_recovery_item_check__outside", None, (Target(UiScreen.STAGE_CHOSEN),), 15.0
                ),
            )
        ),
        UiScreen.STAGE_ALLOW_LIST: ScreenChart(
            transitions=(
                Transition(
                    "stage_allow_list__close",
                    RatioRect(0.429, 0.867, 0.58, 0.97),
                    (Target(UiScreen.ETERNAL_STAGE_LIST),),
                    3.0,
                ),
            )
        ),
        UiScreen.DROP_REWARD_RESULT: ScreenChart(
            transitions=(
                Transition(
                    "drop_reward_result__sortie_again",
                    RatioRect(0.608, 0.861, 0.759, 0.964),
                    (Target(UiScreen.BATTLE_INFO_PREVIEW),),
                    15.0,
                ),
                Transition(
                    "drop_reward_result__select_stage",
                    RatioRect(0.768, 0.861, 0.92, 0.964),
                    (Target(UiScreen.STORY_STAGE_LIST),),
                    14.0,
                ),
            )
        ),
        UiScreen.REWARD_DETAIL: ScreenChart(
            transitions=(
                Transition(
                    "reward_detail__close",
                    RatioRect(0.428, 0.737, 0.58, 0.835),
                    (Target(UiScreen.SKIP_RESULT_LIST),),
                    3.0,
                ),
            )
        ),
        UiScreen.PLAYER_PHASE_OVERVIEW: ScreenChart(
            elements=frozenset({UiElement.TURN_BOX, UiElement.MENU_KEY}),
            transitions=(
                Transition(
                    "player_phase_overview__battle_menu",
                    RatioRect(0.913, 0.016, 0.941, 0.081),
                    (Target(UiScreen.BATTLE_MAIN_SETTING, "battle_menu"),),
                    3.0,
                ),
                Transition(
                    "player_phase_overview__unit_card",
                    RatioRect(0.244, 0.758, 0.385, 0.943),
                    (Target(UiScreen.SELECT_ACTION_IN_BATTLE),),
                    4.6,
                ),
                Transition(
                    "player_phase_overview__map_ally_unit",
                    None,
                    (Target(UiScreen.SELECT_ACTION_IN_BATTLE),),
                    4.6,
                ),
                Transition(
                    "player_phase_overview__end_turn",
                    RatioRect(0.066, 0.139, 0.188, 0.2),
                    (Target(UiScreen.NON_PLAYER_PHASE_BATTLE_VIEW),),
                    4.6,
                ),
            ),
            auto=AutoButton(
                "player_phase_overview__auto", RatioRect(0.743, 0.016, 0.812, 0.079), 15.0
            ),
        ),
        UiScreen.SELECT_ACTION_IN_BATTLE: ScreenChart(
            elements=frozenset({UiElement.TURN_BOX, UiElement.MENU_KEY}),
            transitions=(
                Transition(
                    "select_action_in_battle__battle_menu",
                    RatioRect(0.913, 0.016, 0.941, 0.081),
                    (Target(UiScreen.BATTLE_MAIN_SETTING, "battle_menu"),),
                    3.0,
                ),
                Transition(
                    "select_action_in_battle__enemy_unit_icon",
                    None,
                    (
                        Target(UiScreen.UNIT_DETAIL_STATE, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_ACTION, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_ABILITY, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_SUMMARY, "unit_detail"),
                    ),
                    15.0,
                ),
                Transition(
                    "select_action_in_battle__ally_unit_icon",
                    None,
                    (
                        Target(UiScreen.UNIT_DETAIL_STATE, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_ACTION, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_ABILITY, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_SUMMARY, "unit_detail"),
                    ),
                    4.5,
                ),
                Transition(
                    "select_action_in_battle__prev_unit",
                    RatioRect(0.077, 0.812, 0.122, 0.91),
                    (Target(UiScreen.SELECT_ACTION_IN_BATTLE),),
                    15.0,
                ),
                Transition(
                    "select_action_in_battle__next_unit",
                    RatioRect(0.129, 0.812, 0.174, 0.91),
                    (Target(UiScreen.SELECT_ACTION_IN_BATTLE),),
                    15.0,
                ),
                Transition(
                    "select_action_in_battle__map_ally_unit",
                    None,
                    (Target(UiScreen.SELECT_ACTION_IN_BATTLE),),
                    15.0,
                ),
                Transition(
                    "select_action_in_battle__skill_slot",
                    RatioRect(0.386, 0.791, 0.568, 0.932),
                    (Target(UiScreen.SELECT_SKILL_IN_BATTLE),),
                    3.1,
                ),
                Transition(
                    "select_action_in_battle__wait",
                    RatioRect(0.878, 0.558, 0.915, 0.666),
                    (
                        Target(UiScreen.PLAYER_PHASE_OVERVIEW),
                        Target(UiScreen.NON_PLAYER_PHASE_BATTLE_VIEW),
                    ),
                    15.0,
                ),
                Transition(
                    "select_action_in_battle__back",
                    RatioRect(0.735, 0.823, 0.808, 0.975),
                    (Target(UiScreen.PLAYER_PHASE_OVERVIEW),),
                    6.1,
                ),
                Transition(
                    "select_action_in_battle__select_weapon",
                    RatioRect(0.82, 0.726, 0.935, 0.975),
                    (Target(UiScreen.SELECT_WEAPON_IN_BATTLE),),
                    6.0,
                ),
            ),
            auto=AutoButton(
                "select_action_in_battle__auto", RatioRect(0.743, 0.016, 0.811, 0.081), 15.0
            ),
        ),
        UiScreen.SELECT_SKILL_IN_BATTLE: ScreenChart(
            elements=frozenset({UiElement.TURN_BOX, UiElement.MENU_KEY}),
            transitions=(
                Transition(
                    "select_skill_in_battle__back",
                    RatioRect(0.735, 0.823, 0.808, 0.975),
                    (
                        Target(UiScreen.SELECT_ACTION_IN_BATTLE),
                        Target(UiScreen.SELECT_WEAPON_IN_BATTLE),
                    ),
                    9.2,
                ),
            ),
            auto=AutoButton(
                "select_skill_in_battle__auto", RatioRect(0.743, 0.016, 0.811, 0.079), 15.0
            ),
        ),
        UiScreen.SELECT_WEAPON_IN_BATTLE: ScreenChart(
            elements=frozenset({UiElement.TURN_BOX, UiElement.MENU_KEY}),
            transitions=(
                Transition(
                    "select_weapon_in_battle__battle_menu",
                    RatioRect(0.913, 0.016, 0.941, 0.081),
                    (Target(UiScreen.BATTLE_MAIN_SETTING, "battle_menu"),),
                    3.1,
                ),
                Transition(
                    "select_weapon_in_battle__enemy_unit_icon",
                    None,
                    (
                        Target(UiScreen.UNIT_DETAIL_STATE, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_ACTION, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_ABILITY, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_SUMMARY, "unit_detail"),
                    ),
                    15.0,
                ),
                Transition(
                    "select_weapon_in_battle__ally_unit_icon",
                    None,
                    (
                        Target(UiScreen.UNIT_DETAIL_STATE, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_ACTION, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_ABILITY, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_SUMMARY, "unit_detail"),
                    ),
                    3.1,
                ),
                Transition(
                    "select_weapon_in_battle__skill",
                    RatioRect(0.814, 0.574, 0.85, 0.68),
                    (Target(UiScreen.SELECT_SKILL_IN_BATTLE),),
                    3.1,
                ),
                Transition(
                    "select_weapon_in_battle__wait",
                    RatioRect(0.878, 0.558, 0.915, 0.666),
                    (
                        Target(UiScreen.NON_PLAYER_PHASE_BATTLE_VIEW),
                        Target(UiScreen.PLAYER_PHASE_OVERVIEW),
                    ),
                    13.7,
                ),
                Transition(
                    "select_weapon_in_battle__back",
                    RatioRect(0.735, 0.823, 0.809, 0.975),
                    (Target(UiScreen.SELECT_ACTION_IN_BATTLE),),
                    13.6,
                ),
                Transition(
                    "select_weapon_in_battle__attack",
                    RatioRect(0.82, 0.726, 0.935, 0.975),
                    (Target(UiScreen.BATTLE_PREP_ATTACK),),
                    6.1,
                ),
            ),
            auto=AutoButton(
                "select_weapon_in_battle__auto", RatioRect(0.743, 0.016, 0.811, 0.079), 15.0
            ),
        ),
        UiScreen.BATTLE_PREP_ATTACK: ScreenChart(
            elements=frozenset({UiElement.TURN_BOX, UiElement.MENU_KEY}),
            transitions=(
                Transition(
                    "battle_prep_attack__battle_menu",
                    RatioRect(0.913, 0.016, 0.942, 0.081),
                    (Target(UiScreen.BATTLE_MAIN_SETTING, "battle_menu"),),
                    38.2,
                ),
                Transition(
                    "battle_prep_attack__enemy_unit_icon",
                    None,
                    (
                        Target(UiScreen.UNIT_DETAIL_STATE, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_ACTION, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_ABILITY, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_SUMMARY, "unit_detail"),
                    ),
                    15.0,
                ),
                Transition(
                    "battle_prep_attack__ally_unit_icon",
                    None,
                    (
                        Target(UiScreen.UNIT_DETAIL_STATE, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_ACTION, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_ABILITY, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_SUMMARY, "unit_detail"),
                    ),
                    3.0,
                ),
                Transition(
                    "battle_prep_attack__pilot_slot",
                    RatioRect(0.335, 0.748, 0.488, 0.969),
                    (Target(UiScreen.SELECT_WEAPON_IN_ATTACK_PREPARE, "battle_prep_action"),),
                    3.0,
                ),
                Transition(
                    "battle_prep_attack__pilot_list",
                    RatioRect(0.289, 0.82, 0.319, 0.886),
                    (Target(UiScreen.BATTLE_PREP_DETAIL, "battle_prep_detail"),),
                    4.5,
                ),
                Transition(
                    "battle_prep_attack__back",
                    RatioRect(0.736, 0.821, 0.809, 0.975),
                    (Target(UiScreen.SELECT_WEAPON_IN_BATTLE),),
                    7.6,
                ),
                Transition(
                    "battle_prep_attack__start_battle",
                    RatioRect(0.82, 0.724, 0.935, 0.975),
                    (
                        Target(UiScreen.CHALLENGE_BATTLE_CHECK),
                        Target(UiScreen.NON_PLAYER_PHASE_BATTLE_VIEW),
                        Target(UiScreen.PLAYER_PHASE_OVERVIEW),
                        Target(UiScreen.SELECT_ACTION_IN_BATTLE),
                        Target(UiScreen.BATTLE_SCORE_RESULT),
                    ),
                    16.7,
                ),
            ),
            auto=AutoButton(
                "battle_prep_attack__auto", RatioRect(0.743, 0.016, 0.811, 0.081), 15.0
            ),
        ),
        UiScreen.NON_PLAYER_PHASE_BATTLE_VIEW: ScreenChart(
            elements=frozenset({UiElement.TURN_BOX, UiElement.MENU_KEY}),
            auto=AutoButton(
                "non_player_phase_battle_view__auto", RatioRect(0.743, 0.016, 0.811, 0.079), 15.0
            ),
            waits=(
                Target(UiScreen.BATTLE_PREP_RESPONSE_ATTACK),
                Target(UiScreen.EXP_REWARD_RESULT),
                Target(UiScreen.PLAYER_PHASE_OVERVIEW),
                Target(UiScreen.BATTLE_SCORE_RESULT),
            ),
        ),
        UiScreen.BATTLE_PREP_RESPONSE_ATTACK: ScreenChart(
            elements=frozenset({UiElement.TURN_BOX, UiElement.MENU_KEY}),
            transitions=(
                Transition(
                    "battle_prep_response_attack__enemy_unit_icon",
                    None,
                    (
                        Target(UiScreen.UNIT_DETAIL_STATE, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_ACTION, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_ABILITY, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_SUMMARY, "unit_detail"),
                    ),
                    15.0,
                ),
                Transition(
                    "battle_prep_response_attack__ally_unit_icon",
                    None,
                    (
                        Target(UiScreen.UNIT_DETAIL_STATE, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_ACTION, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_ABILITY, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_SUMMARY, "unit_detail"),
                    ),
                    3.0,
                ),
                Transition(
                    "battle_prep_response_attack__stance_slot",
                    RatioRect(0.334, 0.764, 0.488, 0.954),
                    (Target(UiScreen.SELECT_WEAPON_IN_BATTLE_RESPONSE),),
                    3.1,
                ),
                Transition(
                    "battle_prep_response_attack__stance_list",
                    RatioRect(0.289, 0.821, 0.319, 0.885),
                    (Target(UiScreen.BATTLE_PREP_DETAIL, "battle_prep_detail"),),
                    3.0,
                ),
                Transition(
                    "battle_prep_response_attack__start_battle",
                    RatioRect(0.82, 0.726, 0.935, 0.972),
                    (
                        Target(UiScreen.NON_PLAYER_PHASE_BATTLE_VIEW),
                        Target(UiScreen.BATTLE_SCORE_RESULT),
                    ),
                    3.1,
                ),
            ),
            auto=AutoButton(
                "battle_prep_response_attack__auto", RatioRect(0.743, 0.016, 0.811, 0.079), 15.0
            ),
        ),
        UiScreen.SELECT_WEAPON_IN_BATTLE_RESPONSE: ScreenChart(
            elements=frozenset({UiElement.TURN_BOX, UiElement.MENU_KEY}),
            transitions=(
                Transition(
                    "select_weapon_in_battle_response__confirm",
                    RatioRect(0.82, 0.723, 0.935, 0.969),
                    (
                        Target(UiScreen.NON_PLAYER_PHASE_BATTLE_VIEW),
                        Target(UiScreen.BATTLE_PREP_RESPONSE_ATTACK),
                        Target(UiScreen.BATTLE_SCORE_RESULT),
                    ),
                    4.6,
                ),
            ),
            auto=AutoButton(
                "select_weapon_in_battle_response__auto", RatioRect(0.743, 0.016, 0.811, 0.08), 15.0
            ),
        ),
        UiScreen.SELECT_WEAPON_IN_ATTACK_PREPARE: ScreenChart(
            elements=frozenset({UiElement.TURN_BOX, UiElement.MENU_KEY}),
            transitions=(
                Transition(
                    "select_weapon_in_attack_prepare__skill",
                    RatioRect(0.814, 0.574, 0.85, 0.68),
                    (Target(UiScreen.SELECT_SKILL_IN_ATTACK_PREPARE),),
                    3.1,
                ),
                Transition(
                    "select_weapon_in_attack_prepare__back",
                    RatioRect(0.736, 0.821, 0.809, 0.975),
                    (Target(UiScreen.BATTLE_PREP_ATTACK),),
                    4.6,
                ),
                Transition(
                    "select_weapon_in_attack_prepare__confirm",
                    RatioRect(0.82, 0.724, 0.935, 0.975),
                    (Target(UiScreen.BATTLE_PREP_ATTACK),),
                    4.6,
                ),
            ),
            auto=AutoButton(
                "select_weapon_in_attack_prepare__auto", RatioRect(0.743, 0.016, 0.811, 0.081), 15.0
            ),
        ),
        UiScreen.SELECT_SKILL_IN_ATTACK_PREPARE: ScreenChart(
            transitions=(
                Transition(
                    "select_skill_in_attack_prepare__back",
                    RatioRect(0.735, 0.823, 0.808, 0.975),
                    (Target(UiScreen.SELECT_WEAPON_IN_ATTACK_PREPARE),),
                    4.6,
                ),
                Transition(
                    "select_skill_in_attack_prepare__activate",
                    RatioRect(0.82, 0.726, 0.935, 0.975),
                    (Target(UiScreen.BATTLE_PREP_ATTACK),),
                    4.6,
                ),
            ),
            auto=AutoButton(
                "select_skill_in_attack_prepare__auto", RatioRect(0.743, 0.016, 0.811, 0.079), 15.0
            ),
        ),
        UiScreen.BATTLE_MAIN_SETTING: ScreenChart(
            transitions=(
                Transition(
                    "battle_main_setting__win_condition",
                    RatioRect(0.149, 0.439, 0.257, 0.504),
                    (Target(UiScreen.WIN_CONDITION_OVERLAY),),
                    15.0,
                ),
                Transition(
                    "battle_main_setting__squad_info",
                    RatioRect(0.269, 0.439, 0.376, 0.504),
                    (Target(UiScreen.ROSTER_LIST_ALLY),),
                    15.0,
                ),
                Transition(
                    "battle_main_setting__settings",
                    RatioRect(0.644, 0.755, 0.751, 0.818),
                    (Target(UiScreen.BATTLE_SETTINGS_IN_BATTLE),),
                    15.0,
                ),
                Transition(
                    "battle_main_setting__close",
                    RatioRect(0.428, 0.867, 0.58, 0.972),
                    (
                        Target(UiScreen.SELECT_WEAPON_IN_BATTLE),
                        Target(UiScreen.BATTLE_PREP_ATTACK),
                        Target(UiScreen.BATTLE_INFO_PREVIEW),
                        Target(UiScreen.PLAYER_PHASE_OVERVIEW),
                        Target(UiScreen.SELECT_ACTION_IN_BATTLE),
                    ),
                    15.0,
                ),
            )
        ),
        UiScreen.BATTLE_SETTINGS_IN_BATTLE: ScreenChart(
            transitions=(
                Transition(
                    "battle_settings_in_battle__close",
                    RatioRect(0.429, 0.867, 0.58, 0.971),
                    (Target(UiScreen.BATTLE_MAIN_SETTING, "battle_menu"),),
                    15.0,
                ),
            )
        ),
        UiScreen.BATTLE_PREP_DETAIL: ScreenChart(
            transitions=(
                Transition(
                    "battle_prep_detail__cancel",
                    RatioRect(0.349, 0.87, 0.5, 0.975),
                    (
                        Target(UiScreen.BATTLE_PREP_ATTACK),
                        Target(UiScreen.BATTLE_PREP_RESPONSE_ATTACK),
                    ),
                    3.0,
                ),
                Transition(
                    "battle_prep_detail__select",
                    RatioRect(0.509, 0.87, 0.661, 0.975),
                    (
                        Target(UiScreen.BATTLE_PREP_ATTACK),
                        Target(UiScreen.BATTLE_PREP_RESPONSE_ATTACK),
                    ),
                    3.0,
                ),
            )
        ),
        UiScreen.BATTLE_INFO_PREVIEW: ScreenChart(
            elements=frozenset({UiElement.MENU_KEY}),
            transitions=(
                Transition(
                    "battle_info_preview__battle_menu",
                    RatioRect(0.912, 0.016, 0.942, 0.081),
                    (Target(UiScreen.BATTLE_MAIN_SETTING, "battle_menu"),),
                    15.0,
                ),
                Transition(
                    "battle_info_preview__tap_next",
                    RatioRect(0.0, 0.0, 1.0, 1.0),
                    (Target(UiScreen.PLAYER_PHASE_OVERVIEW),),
                    9.1,
                ),
            ),
            auto=AutoButton(
                "battle_info_preview__auto", RatioRect(0.742, 0.016, 0.812, 0.081), 15.0
            ),
        ),
        UiScreen.CHALLENGE_BATTLE_CHECK: ScreenChart(
            elements=frozenset({UiElement.MENU_KEY}),
            transitions=(
                Transition(
                    "challenge_battle_check__challenge",
                    RatioRect(0.508, 0.854, 0.661, 0.96),
                    (Target(UiScreen.PLAYER_PHASE_OVERVIEW),),
                    9.2,
                ),
            ),
            auto=AutoButton(
                "challenge_battle_check__auto", RatioRect(0.743, 0.016, 0.812, 0.081), 15.0
            ),
        ),
        UiScreen.EXP_REWARD_RESULT: ScreenChart(
            transitions=(
                Transition(
                    "exp_reward_result__next",
                    RatioRect(0.773, 0.861, 0.925, 0.964),
                    (Target(UiScreen.DROP_REWARD_RESULT),),
                    4.7,
                ),
            )
        ),
        UiScreen.BATTLE_SCORE_RESULT: ScreenChart(
            transitions=(
                Transition(
                    "battle_score_result__next",
                    RatioRect(0.773, 0.863, 0.925, 0.964),
                    (Target(UiScreen.EXP_REWARD_RESULT),),
                    3.0,
                ),
            )
        ),
        UiScreen.WIN_CONDITION_OVERLAY: ScreenChart(
            transitions=(
                Transition(
                    "win_condition_overlay__close",
                    RatioRect(0.428, 0.867, 0.58, 0.972),
                    (Target(UiScreen.BATTLE_MAIN_SETTING, "battle_menu"),),
                    15.0,
                ),
            )
        ),
        UiScreen.ROSTER_LIST_ALLY: ScreenChart(
            transitions=(
                Transition(
                    "roster_list_ally__tab_enemy",
                    RatioRect(0.16, 0.53, 0.235, 0.59),
                    (Target(UiScreen.ROSTER_LIST_ENEMY),),
                    15.0,
                ),
                Transition(
                    "roster_list_ally__mech_card",
                    RatioRect(0.288, 0.191, 0.339, 0.301),
                    (
                        Target(UiScreen.UNIT_DETAIL_STATE_ROSTER, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_ACTION_ROSTER, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_ABILITY_ROSTER, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_SUMMARY_ROSTER, "unit_detail"),
                    ),
                    15.0,
                ),
                Transition(
                    "roster_list_ally__close",
                    RatioRect(0.429, 0.867, 0.58, 0.972),
                    (Target(UiScreen.BATTLE_MAIN_SETTING, "battle_menu"),),
                    15.0,
                ),
            )
        ),
        UiScreen.ROSTER_LIST_ENEMY: ScreenChart(
            transitions=(
                Transition(
                    "roster_list_enemy__tab_ally", None, (Target(UiScreen.ROSTER_LIST_ALLY),), 15.0
                ),
                Transition(
                    "roster_list_enemy__mech_card",
                    None,
                    (
                        Target(UiScreen.UNIT_DETAIL_STATE_ROSTER, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_ACTION_ROSTER, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_ABILITY_ROSTER, "unit_detail"),
                        Target(UiScreen.UNIT_DETAIL_SUMMARY_ROSTER, "unit_detail"),
                    ),
                    15.0,
                ),
                Transition(
                    "roster_list_enemy__close",
                    None,
                    (Target(UiScreen.BATTLE_MAIN_SETTING, "battle_menu"),),
                    15.0,
                ),
            )
        ),
        UiScreen.UNIT_DETAIL_STATE: ScreenChart(
            transitions=(
                Transition(
                    "unit_detail_state__close",
                    RatioRect(0.429, 0.867, 0.58, 0.97),
                    (
                        Target(UiScreen.BATTLE_PREP_ATTACK),
                        Target(UiScreen.BATTLE_PREP_RESPONSE_ATTACK),
                        Target(UiScreen.SELECT_ACTION_IN_BATTLE),
                        Target(UiScreen.SELECT_WEAPON_IN_BATTLE),
                    ),
                    15.0,
                ),
            )
        ),
        UiScreen.UNIT_DETAIL_ACTION: ScreenChart(
            transitions=(
                Transition(
                    "unit_detail_action__close",
                    RatioRect(0.429, 0.867, 0.58, 0.972),
                    (
                        Target(UiScreen.BATTLE_PREP_ATTACK),
                        Target(UiScreen.BATTLE_PREP_RESPONSE_ATTACK),
                        Target(UiScreen.SELECT_ACTION_IN_BATTLE),
                        Target(UiScreen.SELECT_WEAPON_IN_BATTLE),
                    ),
                    15.0,
                ),
            )
        ),
        UiScreen.UNIT_DETAIL_ABILITY: ScreenChart(
            transitions=(
                Transition(
                    "unit_detail_ability__close",
                    RatioRect(0.429, 0.867, 0.58, 0.97),
                    (
                        Target(UiScreen.BATTLE_PREP_ATTACK),
                        Target(UiScreen.BATTLE_PREP_RESPONSE_ATTACK),
                        Target(UiScreen.SELECT_ACTION_IN_BATTLE),
                        Target(UiScreen.SELECT_WEAPON_IN_BATTLE),
                    ),
                    15.0,
                ),
            )
        ),
        UiScreen.UNIT_DETAIL_SUMMARY: ScreenChart(
            transitions=(
                Transition(
                    "unit_detail_summary__close",
                    RatioRect(0.429, 0.867, 0.58, 0.97),
                    (
                        Target(UiScreen.BATTLE_PREP_ATTACK),
                        Target(UiScreen.BATTLE_PREP_RESPONSE_ATTACK),
                        Target(UiScreen.SELECT_ACTION_IN_BATTLE),
                        Target(UiScreen.SELECT_WEAPON_IN_BATTLE),
                    ),
                    15.0,
                ),
            )
        ),
        UiScreen.UNIT_DETAIL_STATE_ROSTER: ScreenChart(
            transitions=(
                Transition(
                    "unit_detail_state_roster__close",
                    None,
                    (
                        Target(UiScreen.ROSTER_LIST_ALLY),
                        Target(UiScreen.ROSTER_LIST_ENEMY),
                    ),
                    15.0,
                ),
                Transition(
                    "unit_detail_state_roster__select",
                    None,
                    (Target(UiScreen.SELECT_ACTION_IN_BATTLE),),
                    15.0,
                ),
            )
        ),
        UiScreen.UNIT_DETAIL_ACTION_ROSTER: ScreenChart(
            transitions=(
                Transition(
                    "unit_detail_action_roster__close",
                    None,
                    (
                        Target(UiScreen.ROSTER_LIST_ALLY),
                        Target(UiScreen.ROSTER_LIST_ENEMY),
                    ),
                    15.0,
                ),
                Transition(
                    "unit_detail_action_roster__select",
                    None,
                    (Target(UiScreen.SELECT_ACTION_IN_BATTLE),),
                    15.0,
                ),
            )
        ),
        UiScreen.UNIT_DETAIL_ABILITY_ROSTER: ScreenChart(
            transitions=(
                Transition(
                    "unit_detail_ability_roster__close",
                    None,
                    (
                        Target(UiScreen.ROSTER_LIST_ALLY),
                        Target(UiScreen.ROSTER_LIST_ENEMY),
                    ),
                    15.0,
                ),
                Transition(
                    "unit_detail_ability_roster__select",
                    None,
                    (Target(UiScreen.SELECT_ACTION_IN_BATTLE),),
                    15.0,
                ),
            )
        ),
        UiScreen.UNIT_DETAIL_SUMMARY_ROSTER: ScreenChart(
            transitions=(
                Transition(
                    "unit_detail_summary_roster__close",
                    None,
                    (
                        Target(UiScreen.ROSTER_LIST_ALLY),
                        Target(UiScreen.ROSTER_LIST_ENEMY),
                    ),
                    15.0,
                ),
                Transition(
                    "unit_detail_summary_roster__select",
                    None,
                    (Target(UiScreen.SELECT_ACTION_IN_BATTLE),),
                    15.0,
                ),
            )
        ),
        UiScreen.MECH_NORMAL_INFO: ScreenChart(
            transitions=(
                Transition(
                    "mech_normal_info__close",
                    RatioRect(0.429, 0.867, 0.58, 0.97),
                    (
                        Target(UiScreen.BATTLE_PREP_ATTACK),
                        Target(UiScreen.BATTLE_PREP_RESPONSE_ATTACK),
                        Target(UiScreen.SELECT_ACTION_IN_BATTLE),
                        Target(UiScreen.SELECT_WEAPON_IN_BATTLE),
                    ),
                    15.0,
                ),
            )
        ),
        UiScreen.PILOT_NORMAL_INFO: ScreenChart(
            transitions=(
                Transition(
                    "pilot_normal_info__close",
                    RatioRect(0.428, 0.867, 0.58, 0.972),
                    (
                        Target(UiScreen.BATTLE_PREP_ATTACK),
                        Target(UiScreen.BATTLE_PREP_RESPONSE_ATTACK),
                        Target(UiScreen.SELECT_ACTION_IN_BATTLE),
                        Target(UiScreen.SELECT_WEAPON_IN_BATTLE),
                    ),
                    15.0,
                ),
            )
        ),
        UiScreen.WEAPON_INFO: ScreenChart(
            transitions=(
                Transition(
                    "weapon_info__close",
                    RatioRect(0.429, 0.867, 0.58, 0.972),
                    (
                        Target(UiScreen.BATTLE_PREP_ATTACK),
                        Target(UiScreen.BATTLE_PREP_RESPONSE_ATTACK),
                        Target(UiScreen.SELECT_ACTION_IN_BATTLE),
                        Target(UiScreen.SELECT_WEAPON_IN_BATTLE),
                    ),
                    15.0,
                ),
            )
        ),
    },
    groups=(
        Group(
            "unit_detail",
            frozenset(
                {
                    UiScreen.UNIT_DETAIL_STATE,
                    UiScreen.UNIT_DETAIL_ACTION,
                    UiScreen.UNIT_DETAIL_ABILITY,
                    UiScreen.UNIT_DETAIL_SUMMARY,
                    UiScreen.UNIT_DETAIL_STATE_ROSTER,
                    UiScreen.UNIT_DETAIL_ACTION_ROSTER,
                    UiScreen.UNIT_DETAIL_ABILITY_ROSTER,
                    UiScreen.UNIT_DETAIL_SUMMARY_ROSTER,
                }
            ),
            frozenset(
                {
                    UiScreen.UNIT_DETAIL_STATE,
                    UiScreen.UNIT_DETAIL_ACTION,
                    UiScreen.UNIT_DETAIL_ABILITY,
                    UiScreen.UNIT_DETAIL_SUMMARY,
                    UiScreen.UNIT_DETAIL_STATE_ROSTER,
                    UiScreen.UNIT_DETAIL_ACTION_ROSTER,
                    UiScreen.UNIT_DETAIL_ABILITY_ROSTER,
                    UiScreen.UNIT_DETAIL_SUMMARY_ROSTER,
                    UiScreen.MECH_NORMAL_INFO,
                    UiScreen.PILOT_NORMAL_INFO,
                    UiScreen.WEAPON_INFO,
                }
            ),
        ),
        Group(
            "ap_recovery",
            frozenset({UiScreen.AP_RECOVERY_OVERLAY}),
            frozenset({UiScreen.AP_RECOVERY_OVERLAY, UiScreen.AP_RECOVERY_ITEM_CHECK}),
        ),
        Group(
            "battle_menu",
            frozenset({UiScreen.BATTLE_MAIN_SETTING}),
            frozenset(
                {
                    UiScreen.BATTLE_MAIN_SETTING,
                    UiScreen.BATTLE_SETTINGS_IN_BATTLE,
                    UiScreen.WIN_CONDITION_OVERLAY,
                    UiScreen.ROSTER_LIST_ALLY,
                    UiScreen.ROSTER_LIST_ENEMY,
                }
            ),
        ),
        Group(
            "battle_prep_detail",
            frozenset({UiScreen.BATTLE_PREP_DETAIL}),
            frozenset({UiScreen.BATTLE_PREP_DETAIL}),
        ),
        Group(
            "battle_prep_action",
            frozenset({UiScreen.SELECT_WEAPON_IN_ATTACK_PREPARE}),
            frozenset(
                {UiScreen.SELECT_WEAPON_IN_ATTACK_PREPARE, UiScreen.SELECT_SKILL_IN_ATTACK_PREPARE}
            ),
        ),
    ),
)
