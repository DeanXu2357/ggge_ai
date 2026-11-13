from __future__ import annotations

from ggge_ai_2.screenmodel.contract import MapRequest, ModelElement, ModelScreen
from ggge_ai_2.screenmodel.definition import Need, ScreenDefinition

# The definition does not use the lit menu key of section 2.4 rule 3. With AUTO on, the menu
# key is dark on this screen too (4 of 4 labeled frames).
DEFINITION = ScreenDefinition(
    ModelScreen.PLAYER_PHASE_OVERVIEW,
    (Need(ModelElement.TURN_BOX), Need(ModelElement.TOP_LEFT_TITLE, "player_phase")),
    phase=True,
    map=MapRequest(chevrons=True),
)
