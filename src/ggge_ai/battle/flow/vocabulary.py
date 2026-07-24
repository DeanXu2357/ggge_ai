"""Translator: a single captured frame (+ the recognizer probe + the run-scoped
blackboard) -> a ``goap`` WorldState the flow planner reasons over.

Three-value discipline (定案 1): ``unknown`` is a first-class value. When a
predicate cannot be read honestly -- the map is covered, no lattice is on
screen, the frame is missing -- it reports ``unknown`` and NEVER guesses one of
the known values. Planning on ``unknown`` is safe because every action is an
idempotent ensure (set-to-target), so the worst case is one extra cheap step.

Perception predicates are re-read every tick from the frame; progress
predicates (census_built, sim_synced ...) are merged in from the blackboard.
Round 2.0 ships only the perception predicates and passes any blackboard facts
straight through, so the Round 2.1 macro actions have their hook already.
"""

from __future__ import annotations

from collections.abc import Mapping

from ...goap.state import Value, WorldState
from .. import map_view, vision

# predicate keys
VIEW = "view"
UNIT_LIST = "unit_list"
GRID = "grid"
ZOOM = "zoom"
OBSTRUCTION = "obstruction"

# the shared honest "cannot read" value across every predicate
UNKNOWN = "unknown"

# view values are exactly map_view.classify_frame's closed vocabulary
# (hub / unit_move / weapon_select / skill / battle_prep / modal / settings /
# unknown); the flow only names the ones it plans against.
VIEW_HUB = map_view.HUB

# unit_list values are vision.unit_list_state's (批8, consumed directly)
UNIT_LIST_EXPANDED = vision.UNIT_LIST_EXPANDED
UNIT_LIST_COLLAPSED = vision.UNIT_LIST_COLLAPSED

GRID_ON = "on"
GRID_OFF = "off"

ZOOM_MAX = "max"
ZOOM_NOT_MAX = "not_max"

OBSTRUCTION_NONE = "none"
OBSTRUCTION_MODAL = "modal"
OBSTRUCTION_SELECTION = "selection_residue"
# reserved value: a dimmed/overlay obstruction has no calibrated detector yet
# (no fixture佐證). It stays in the domain so a future detector slots in
# without a vocabulary change, but v1 never emits it (缺樣, see tests).
OBSTRUCTION_DIMMED = "dimmed"

# the obstruction states the tick loop can repair; a view=unknown frame that
# also carries one of these should replan to clear it, not wait it out.
CLEARABLE_OBSTRUCTIONS = frozenset({OBSTRUCTION_MODAL, OBSTRUCTION_SELECTION})


def _obstruction(frame) -> str:
    """modal veto first (it dims the whole map), then the R1.7 enemy-selection
    residue; a clean frame is "none". dimmed is not detected in v1."""
    if vision.is_unit_detail_modal(frame):
        return OBSTRUCTION_MODAL
    if vision.enemy_selection_active(frame):
        return OBSTRUCTION_SELECTION
    return OBSTRUCTION_NONE


def _grid(frame, view: str) -> str:
    """on/off only where the battle map is cleanly visible (view=hub, central
    band clear); off-hub the lattice reader would false-negative on an overlay,
    so report unknown. "on" mirrors ensure_battle_grid's ground truth
    (read_grid_lattice found a lattice)."""
    if view != VIEW_HUB:
        return UNKNOWN
    return GRID_ON if vision.read_grid_lattice(frame) is not None else GRID_OFF


def _zoom(frame, grid: str) -> str:
    """max/not_max derived from the grid pitch; unknown whenever the grid is not
    known-on (no lattice to measure -- "格線 off 時 unknown")."""
    if grid != GRID_ON:
        return UNKNOWN
    verdict = vision.zoom_at_max(frame)
    if verdict is True:
        return ZOOM_MAX
    if verdict is False:
        return ZOOM_NOT_MAX
    return UNKNOWN


def translate(
    frame, probe, progress: Mapping[str, Value] | None = None
) -> WorldState:
    """frame (+ probe for the label templates) + blackboard progress ->
    WorldState. A missing frame (capture failure) makes every perception
    predicate honestly ``unknown`` rather than crashing a reader on None."""
    if frame is None:
        facts: dict[str, Value] = {
            VIEW: UNKNOWN,
            UNIT_LIST: UNKNOWN,
            GRID: UNKNOWN,
            ZOOM: UNKNOWN,
            OBSTRUCTION: UNKNOWN,
        }
    else:
        view = map_view.classify_frame(frame, probe)
        obstruction = _obstruction(frame)
        unit_list = vision.unit_list_state(frame)
        grid = _grid(frame, view)
        zoom = _zoom(frame, grid)
        facts = {
            VIEW: view,
            UNIT_LIST: unit_list,
            GRID: grid,
            ZOOM: zoom,
            OBSTRUCTION: obstruction,
        }
    if progress:
        facts.update(progress)
    return WorldState(facts)
