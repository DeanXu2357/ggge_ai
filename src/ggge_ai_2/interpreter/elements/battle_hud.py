from __future__ import annotations

from ggge_ai_2.screenmodel.contract import Rect

# Each search rectangle holds the template where the game draws it, with a margin of 16 px.
# Each box is the element around the match, as offsets from the top left of the match.
TEMPLATE_SCORE = 0.7
MENU_KEY_SEARCH: Rect = (2136, 21, 2202, 84)
MENU_KEY_BOX: Rect = (-8, -7, 52, 53)
END_TURN_SEARCH: Rect = (224, 149, 376, 218)
END_TURN_BOX: Rect = (-90, -20, 202, 57)
CHANGE_DEPLOY_SEARCH: Rect = (219, 252, 421, 312)
CHANGE_DEPLOY_BOX: Rect = (-85, -23, 207, 50)
# The prompt is above the card row. It moves down to y=987 when the card row closes.
PROMPT_SEARCH: Rect = (204, 736, 556, 1043)
PROMPT_BOX: Rect = (-25, -14, 1020, 50)
BACK_SEARCH: Rect = (1749, 914, 1861, 1031)
BACK_BOX: Rect = (-8, -8, 88, 93)
STANDBY_SEARCH: Rect = (2044, 599, 2156, 706)
STANDBY_BOX: Rect = (-8, -8, 88, 83)
SKILL_SEARCH: Rect = (1896, 599, 2000, 751)
SKILL_BOX: Rect = (-8, -8, 80, 128)
SWITCH_TARGET_SEARCH: Rect = (1756, 702, 1908, 848)
SWITCH_TARGET_BOX: Rect = (-8, -8, 128, 122)
SWITCH_UNIT_SEARCH: Rect = (184, 879, 276, 981)
SWITCH_UNIT_BOX: Rect = (-32, -27, 222, 173)
# The arrows are thin lines over the map, so the match score stays lower than for the
# other elements.
SWITCH_UNIT_SCORE = 0.5
