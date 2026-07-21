"""Battle-map view state: recognise where the UI is and back out to the
top-level our-turn hub so the whole map is visible (max zoom-out target).

User's call (2026-07-20): before zooming the map, if the screen is NOT the
top-level hub with the actionable-unit list collapsed, return to that top
level -- a selected unit's move/attack overlay (and any sub-menu) both shrink
the visible map and, worse, sit one tap away from committing a unit's action.

Recognition reuses the existing phase-label templates through
``perception.probe`` (label_our_turn = hub; label_unit_move / _weapon_select /
_skill = a unit is selected). The only actuation used to back out is the
in-game 返回 button (btn_battle_return), which the game draws ONLY in those
sub-states -- so tapping it is always a safe cancel and never risks the
system back key opening a quit dialog at the hub.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from . import vision

log = logging.getLogger(__name__)

HUB_LABEL = "label_our_turn"
SUBSTATE_LABELS = ("label_unit_move", "label_weapon_select", "label_skill", "label_battle_prep")
ENEMY_TURN_LABEL = "label_enemy_turn"
ALL_LABELS = (HUB_LABEL, *SUBSTATE_LABELS, ENEMY_TURN_LABEL)
RETURN_BUTTON = "btn_battle_return"

# card-strip toggle: ▽(1970,780) collapses an open strip, ▲(1970,1010) expands
UNIT_LIST_COLLAPSE = (1970, 780)
UNIT_DETAIL_CLOSE = (1176, 992)

# classify_frame's return vocabulary, kept as a named closed set: classify_frame
# is meant to grow into the project-wide page classifier (settings / unit-detail
# and other non-battle pages land here in later tasks), so callers match these
# names and never assume the frame is a battle screen.
HUB = "hub"
MODAL = "modal"
UNKNOWN = "unknown"

# winning phase label -> state. A label absent here (the enemy-turn distractor)
# falls through to UNKNOWN, so a non-actionable banner never reads as a page.
_LABEL_STATES: dict[str, str] = {
    HUB_LABEL: HUB,
    **{label: label.removeprefix("label_") for label in SUBSTATE_LABELS},
}

# frame-predicate page detectors, tried in order ahead of the phase-label
# argmax; the first predicate that fires wins. A page that dims the map and
# lets a phase label bleed through (the unit-detail modal) must be caught here,
# before the labels. New non-battle pages slot in as (state, predicate) rows
# without disturbing the argmax below. Predicates resolve the vision function
# at call time (not import time) so the seam stays monkeypatchable.
_PAGE_DETECTORS: tuple[tuple[str, Callable[..., bool]], ...] = (
    (MODAL, lambda frame: vision.is_unit_detail_modal(frame)),
)

# the full closed set of legal classify_frame return values
VIEW_STATES: tuple[str, ...] = (
    *(state for state, _ in _PAGE_DETECTORS),
    HUB,
    *(_LABEL_STATES[label] for label in SUBSTATE_LABELS),
    UNKNOWN,
)


def _center(bbox) -> tuple[int, int]:
    return (int(bbox.x + bbox.w / 2), int(bbox.y + bbox.h / 2))


def classify_frame(frame, detect: Callable[..., dict]) -> str:
    """Classify a single frame into one of VIEW_STATES: "hub" (top-level, safe,
    max view), "modal" (unit-detail popup), a sub-state name ("unit_move"/
    "weapon_select"/"skill"/"battle_prep"), or "unknown" (enemy turn,
    transition, unclassified).

    Pure: ``detect(element_ids, frame=frame) -> dict[id, element]`` is the only
    seam (``perception.probe`` in production, the recognizer in tests). Frame-
    predicate page detectors (_PAGE_DETECTORS) run first because such a page
    dims the map behind itself and a phase label can bleed through; whatever
    none of them claim then resolves by phase-label argmax through _LABEL_STATES,
    with the enemy-turn distractor falling through to "unknown"."""
    for state, detected in _PAGE_DETECTORS:
        if detected(frame):
            return state
    found = detect(ALL_LABELS, frame=frame)
    if not found:
        return UNKNOWN
    best = max(found, key=lambda k: found[k].confidence)
    return _LABEL_STATES.get(best, UNKNOWN)


def classify_view(perception, frame=None) -> str:
    """``classify_frame`` on a captured frame, probing through perception."""
    frame = perception.capture() if frame is None else frame
    return classify_frame(frame, perception.probe)


def is_top_hub(perception, frame=None) -> bool:
    return classify_view(perception, frame) == "hub"


def return_to_top(
    perception,
    actuator,
    *,
    sleep: Callable[[float], None] = time.sleep,
    keyguard=None,
    attempts: int = 6,
    settle_s: float = 1.2,
) -> bool:
    """Cancel back to the our-turn hub. Closes a stray unit-detail modal, taps
    the 返回 button out of any selection sub-state, and nudges the neutral spot
    on an unrecognised frame -- never the system back key, so the hub is never
    at risk of a quit dialog. Fail-soft: returns whether the hub was reached."""
    for _ in range(attempts):
        if keyguard is not None:
            keyguard.ensure_unlocked()
        frame = perception.capture()
        view = classify_view(perception, frame)
        if view == "hub":
            return True
        if view == "modal":
            actuator.tap(*UNIT_DETAIL_CLOSE)
            sleep(settle_s)
            continue
        found = perception.probe([RETURN_BUTTON], frame=frame)
        btn = found.get(RETURN_BUTTON)
        if btn is not None:
            log.info("view=%s: tapping 返回 to cancel to hub", view)
            actuator.tap(*_center(btn.bbox))
        else:
            # unknown with no cancel button visible: a harmless neutral tap can
            # dismiss a transient banner; if it is genuinely the hub the next
            # probe will confirm it. Never blind-press system back here.
            log.info("view=%s, no 返回 button; neutral nudge", view)
            actuator.tap(1170, 90)
        sleep(settle_s)
    return is_top_hub(perception)


def collapse_unit_list(
    perception, actuator, *, sleep: Callable[[float], None] = time.sleep, attempts: int = 2
) -> bool:
    """Collapse the actionable-unit card strip (▽) for the widest map. Returns
    True once the strip is closed."""
    for _ in range(attempts):
        if not vision.unit_cards_present(perception.capture()):
            return True
        actuator.tap(*UNIT_LIST_COLLAPSE)
        sleep(1.2)
    return not vision.unit_cards_present(perception.capture())


def ensure_max_view(
    perception, actuator, *, sleep: Callable[[float], None] = time.sleep, keyguard=None
) -> bool:
    """Put the battle map in its maximum-visibility state: top-level hub with
    the unit-card strip collapsed. Returns True only when the hub was reached
    (the collapse is best-effort on top of it)."""
    if not return_to_top(perception, actuator, sleep=sleep, keyguard=keyguard):
        log.warning("could not reach the our-turn hub; zooming from current view")
        return False
    collapse_unit_list(perception, actuator, sleep=sleep)
    return True
