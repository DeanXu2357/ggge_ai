from __future__ import annotations

import numpy as np

from ggge_ai_2.interpreter.elements.shape import HORIZONTAL, VERTICAL, direction_edges, edge_near
from ggge_ai_2.screenmodel.contract import Rect

CARD_LEFT = 218
CARD_PITCH = 175
CARD_SLOTS = 12
# The box of a card, as offsets from the left of its slot.
CARD_BOX: Rect = (-3, 808, 160, 1025)
# The HP bar sits on the EN bar in a dark frame. The outline is the top of the HP bar, the
# bottom of the EN bar and the two ends of the bars. The two ends are offsets from the left
# of the slot.
BAR_TOP, BAR_BOTTOM = 993, 1022
BAR_LEFT, BAR_RIGHT = 3, 155
BAR_MARGIN = 30
OUTLINE_INSET = 6
OUTLINE_SHARE = 0.8


def unit_cards(image: np.ndarray) -> tuple[Rect, ...]:
    """Return the box of each card in the card row.

    The bar color differs between units (map20261112-26: a teal bar for a story character),
    so the outline of the bars tells that a card is there.
    """
    top = BAR_TOP - BAR_MARGIN
    labels = direction_edges(image[top : BAR_BOTTOM + BAR_MARGIN])
    vertical = edge_near(labels, VERTICAL)
    horizontal = edge_near(labels, HORIZONTAL)
    rows = np.arange(BAR_TOP + OUTLINE_INSET, BAR_BOTTOM - OUTLINE_INSET) - top
    left, card_top, right, card_bottom = CARD_BOX
    cards: list[Rect] = []
    for slot in range(CARD_SLOTS):
        x = CARD_LEFT + CARD_PITCH * slot
        if x + right > image.shape[1]:
            break
        columns = np.arange(x + BAR_LEFT + OUTLINE_INSET, x + BAR_RIGHT - OUTLINE_INSET)
        sides = (
            horizontal[BAR_TOP - top, columns],
            horizontal[BAR_BOTTOM - top, columns],
            vertical[rows, x + BAR_LEFT],
            vertical[rows, x + BAR_RIGHT],
        )
        if min(float(side.mean()) for side in sides) >= OUTLINE_SHARE:
            cards.append((x + left, card_top, x + right, card_bottom))
    return tuple(cards)
