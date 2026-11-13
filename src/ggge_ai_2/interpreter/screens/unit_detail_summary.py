from __future__ import annotations

import numpy as np

from ggge_ai_2.interpreter.contract import Screen
from ggge_ai_2.interpreter.elements.unit_detail import (
    BLOCK_REGIONS,
    BUTTON_REGIONS,
    has_unit_detail_shape,
    has_unit_detail_title,
)

SCREEN = Screen.UNIT_DETAIL_SUMMARY


# The buttons also match the other tabs of the unit detail and 'mech_normal_info'. The title
# also matches the other tabs. Only the blocks are particular to the summary tab.
def quick_check(image: np.ndarray) -> bool:
    return (
        all(has_unit_detail_shape(image, name) for name in BUTTON_REGIONS)
        and has_unit_detail_title(image)
        and all(has_unit_detail_shape(image, name) for name in BLOCK_REGIONS)
    )
