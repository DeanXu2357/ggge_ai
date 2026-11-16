from __future__ import annotations

from enum import StrEnum

import cv2
import numpy as np

from ggge_ai_2.interpreter.elements.region import Region, crop, template

TITLE_REGION: Region = (0.035, 0.012, 0.20, 0.068)
TITLE_MIN_IOU = 0.5


class TopLeftTitle(StrEnum):
    PLAYER_PHASE = "player_phase"
    UNIT_MOVE = "unit_move"
    SELECT_WEAPON = "select_weapon"
    BATTLE_PREP_ATTACK = "battle_prep_attack"
    BATTLE_PREP_RESPONSE = "battle_prep_response"
    ENEMY_PHASE = "enemy_phase"
    SKILL = "skill"


def title_mask(image: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(crop(image, TITLE_REGION), cv2.COLOR_BGR2HSV)
    return (hsv[..., 2] > 225) & (hsv[..., 1] < 30)


def title_ious(image: np.ndarray) -> dict[TopLeftTitle, float]:
    mask = title_mask(image)
    return {title: _iou(mask, template(f"title_{title.value}") > 0) for title in TopLeftTitle}


def top_left_title(image: np.ndarray) -> TopLeftTitle | None:
    ious = title_ious(image)
    best = max(ious, key=lambda title: ious[title])
    return best if ious[best] > TITLE_MIN_IOU else None


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    union = int(np.count_nonzero(a | b))
    return int(np.count_nonzero(a & b)) / union if union else 0.0
