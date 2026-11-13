from __future__ import annotations

from ggge_ai_2.screenmodel.contract import ModelElement, ModelScreen
from ggge_ai_2.screenmodel.definition import Need, ScreenDefinition

DEFINITION = ScreenDefinition(
    ModelScreen.SELECT_WEAPON_IN_ATTACK_PREPARE,
    (
        Need(ModelElement.TURN_BOX),
        Need(ModelElement.TOP_LEFT_TITLE, "battle_prep_attack"),
        Need(ModelElement.ROUND_BUTTON, "select_action"),
    ),
)
