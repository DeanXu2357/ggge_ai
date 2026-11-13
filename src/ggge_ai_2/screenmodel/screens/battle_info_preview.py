from __future__ import annotations

from ggge_ai_2.screenmodel.contract import ModelElement, ModelScreen
from ggge_ai_2.screenmodel.definition import Need, ScreenDefinition

DEFINITION = ScreenDefinition(
    ModelScreen.BATTLE_INFO_PREVIEW,
    (Need(ModelElement.FAST_FORWARD), Need(ModelElement.TAP_TO_NEXT)),
    auto=True,
)
