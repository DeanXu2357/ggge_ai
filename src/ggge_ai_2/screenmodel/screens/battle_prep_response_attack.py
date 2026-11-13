from __future__ import annotations

from ggge_ai_2.screenmodel.contract import ModelElement, ModelScreen
from ggge_ai_2.screenmodel.definition import Need, ScreenDefinition

# The user ruled that the map is not read on the battle prep screens, although they show the
# grid. These screens show a damage preview over the map.
DEFINITION = ScreenDefinition(
    ModelScreen.BATTLE_PREP_RESPONSE_ATTACK,
    (
        Need(ModelElement.TURN_BOX),
        Need(ModelElement.TOP_LEFT_TITLE, "battle_prep_response"),
        Need(ModelElement.ROUND_BUTTON, "start_battle"),
    ),
    phase=True,
)
