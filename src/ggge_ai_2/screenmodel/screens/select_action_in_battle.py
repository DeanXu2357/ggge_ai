from __future__ import annotations

from ggge_ai_2.screenmodel.contract import MapRequest, ModelElement, ModelScreen
from ggge_ai_2.screenmodel.definition import Need, ScreenDefinition

DEFINITION = ScreenDefinition(
    ModelScreen.SELECT_ACTION_IN_BATTLE,
    (Need(ModelElement.TURN_BOX), Need(ModelElement.TOP_LEFT_TITLE, "unit_move")),
    auto=True,
    map=MapRequest(chevrons=False),
)
