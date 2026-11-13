from __future__ import annotations

import cv2
import numpy as np

from ggge_ai_2.screenmodel.contract import Rect

PANEL_ROWS = (135, 255)
# Each panel has two blocks with straight vertical edges. The battle prep screens draw the
# blocks a few pixels apart from the map screens (rec20261014-648: x=563 and x=976 for
# x=554 and x=971), so each edge is the strongest line in a window.
LEFT_PANEL_LINES = ((550, 567), (967, 980))
RIGHT_PANEL_LINES = ((1377, 1388), (1794, 1807))
LINE_AROUND = (5, 20)
LINE_PEAK_RATIO = 7.0
LEFT_PANEL_BOX: Rect = (145, 118, 978, 295)
RIGHT_PANEL_BOX: Rect = (1382, 118, 2215, 295)


def line_peaks(image: np.ndarray, windows: tuple[tuple[int, int], ...]) -> tuple[float, ...]:
    """Return, for each window, the mean horizontal gradient of its strongest column over the
    median gradient beside that column."""
    top, bottom = PANEL_ROWS
    gray = cv2.cvtColor(image[top:bottom], cv2.COLOR_BGR2GRAY).astype(np.float32)
    gradient = np.abs(np.diff(gray, axis=1)).mean(axis=0)
    near, far = LINE_AROUND
    peaks: list[float] = []
    for low, high in windows:
        x = low + int(np.argmax(gradient[low:high]))
        around = np.concatenate([gradient[x - far : x - near], gradient[x + near : x + far]])
        peaks.append(float(gradient[x] / (np.median(around) + 1.0)))
    return tuple(peaks)


def left_unit_panel(image: np.ndarray) -> tuple[Rect, ...]:
    if min(line_peaks(image, LEFT_PANEL_LINES)) < LINE_PEAK_RATIO:
        return ()
    return (LEFT_PANEL_BOX,)


def right_unit_panel(image: np.ndarray) -> tuple[Rect, ...]:
    if min(line_peaks(image, RIGHT_PANEL_LINES)) < LINE_PEAK_RATIO:
        return ()
    return (RIGHT_PANEL_BOX,)
