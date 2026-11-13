from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

import numpy as np

from ggge_ai_2.screenmodel.contract import SeenElement


class ElementDetector(Protocol):
    def detect(self, image: np.ndarray) -> Sequence[SeenElement]:
        """Return an empty sequence when the element is not in the frame.

        An element that the frame shows more than once, for example a unit card, gives one
        result for each place.
        """
        ...
