from __future__ import annotations

import cv2
import numpy as np

from ggge_ai_2.screenmodel.contract import Rect

# The round buttons of the bottom row: the weapons, the skills and the support choices.
BUTTON_SLOTS = (619, 804, 988, 1173, 1357, 1550)
BUTTON_CENTER_Y = 932
BUTTON_RADII = (68, 84)
BUTTON_SEARCH = 16
BUTTON_EDGE = 20.0
BUTTON_SHARE = 0.85
# A disabled button, or a button over the red tint of a weapon range, shows a weaker ring
# (map20261026-40: 0.68 to 0.78). Where no button is, a slot next to the row gives at most
# 0.5 (rec20261014-728).
NEIGHBOR_SHARE = 0.6
# The rows that hold the rings at every searched center.
BUTTON_BAND = (830, 1040)
# The box of a button with its label and its bar, as offsets from the center of its ring.
BUTTON_BOX: Rect = (-96, -92, 96, 148)


def choice_buttons(image: np.ndarray) -> tuple[Rect, ...]:
    """Return the box of each round button in the bottom row, around the center of its ring.

    The row has no empty slot between two buttons, so the row is every slot from the first
    to the last button with a clear ring, and the slots next to it with a weaker ring.
    """
    band_top, band_bottom = BUTTON_BAND
    gray = cv2.cvtColor(image[band_top:band_bottom], cv2.COLOR_BGR2GRAY)
    smooth = cv2.GaussianBlur(gray, (5, 5), 0).astype(np.float32)
    gradient_x = cv2.Sobel(smooth, cv2.CV_32F, 1, 0, ksize=3) / 4
    gradient_y = cv2.Sobel(smooth, cv2.CV_32F, 0, 1, ksize=3) / 4
    rings: list[tuple[float, int, int]] = []
    for x in BUTTON_SLOTS:
        searched = np.array(
            [
                (x + dx, BUTTON_CENTER_Y - band_top + dy)
                for dx in range(-BUTTON_SEARCH, BUTTON_SEARCH + 1, 2)
                for dy in (-4, 0, 4)
            ]
        )
        shares = ring_share(gradient_x, gradient_y, searched, BUTTON_RADII)
        best = int(np.argmax(shares))
        center_x, center_y = (int(value) for value in searched[best])
        rings.append((float(shares[best]), center_x, center_y + band_top))
    clear = [slot for slot, (share, _, _) in enumerate(rings) if share >= BUTTON_SHARE]
    if not clear:
        return ()
    first, last = clear[0], clear[-1]
    while first > 0 and rings[first - 1][0] >= NEIGHBOR_SHARE:
        first -= 1
    while last < len(rings) - 1 and rings[last + 1][0] >= NEIGHBOR_SHARE:
        last += 1
    left, top, right, bottom = BUTTON_BOX
    return tuple((x + left, y + top, x + right, y + bottom) for _, x, y in rings[first : last + 1])


def ring_share(
    gradient_x: np.ndarray, gradient_y: np.ndarray, centers: np.ndarray, radii: tuple[int, int]
) -> np.ndarray:
    """Return, for each center, the best share of directions with a radial edge at one radius.

    A direction counts when the radial gradient is strong within one pixel of the radius.
    """
    angles = np.linspace(0, 2 * np.pi, 72, endpoint=False)
    radius = np.arange(radii[0] - 1, radii[1] + 2)
    cos, sin = np.cos(angles), np.sin(angles)
    height, width = gradient_x.shape
    xs = np.round(centers[:, 0, None, None] + radius[None, :, None] * cos).astype(int)
    ys = np.round(centers[:, 1, None, None] + radius[None, :, None] * sin).astype(int)
    inside = (xs >= 0) & (xs < width) & (ys >= 0) & (ys < height)
    xs, ys = np.clip(xs, 0, width - 1), np.clip(ys, 0, height - 1)
    radial = np.abs(gradient_x[ys, xs] * cos + gradient_y[ys, xs] * sin)
    strong = (radial > BUTTON_EDGE) & inside
    near = strong[:, :-2] | strong[:, 1:-1] | strong[:, 2:]
    return near.mean(axis=2).max(axis=1)
