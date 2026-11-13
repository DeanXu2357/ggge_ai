from __future__ import annotations

from ggge_ai_2.screenmodel.contract import ModelElement, ModelScreen
from ggge_ai_2.screenmodel.definition import Need, ScreenDefinition

# The buttons also match the other tabs of the unit detail and 'mech_normal_info'. The title
# also matches the other tabs. Only the blocks are particular to the summary tab.
DEFINITION = ScreenDefinition(
    ModelScreen.UNIT_DETAIL_SUMMARY,
    (
        Need(ModelElement.UNIT_DETAIL_DETAIL_BUTTON),
        Need(ModelElement.UNIT_DETAIL_CLOSE_BUTTON),
        Need(ModelElement.UNIT_DETAIL_TITLE),
        Need(ModelElement.UNIT_DETAIL_MECH_PANEL),
        Need(ModelElement.UNIT_DETAIL_PILOT_PANEL),
        Need(ModelElement.UNIT_DETAIL_BOX_WEAPONS),
        Need(ModelElement.UNIT_DETAIL_BOX_ABILITIES),
        Need(ModelElement.UNIT_DETAIL_BOX_PARTS),
        Need(ModelElement.UNIT_DETAIL_BOX_PILOT_SKILLS),
        Need(ModelElement.UNIT_DETAIL_BOX_PILOT_ABILITIES),
    ),
)
