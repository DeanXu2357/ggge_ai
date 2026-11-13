from __future__ import annotations

from ggge_ai_2.screenmodel.contract import ModelElement, ModelScreen
from ggge_ai_2.screenmodel.definition import Need, ScreenDefinition

DEFINITION = ScreenDefinition(
    ModelScreen.BATTLE_PREP_ATTACK,
    (
        Need(ModelElement.TURN_BOX),
        Need(ModelElement.TOP_LEFT_TITLE, "battle_prep_attack"),
        Need(ModelElement.ROUND_BUTTON, "start_battle"),
    ),
    phase=True,
)
