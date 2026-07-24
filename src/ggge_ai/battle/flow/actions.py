"""Flow repair / navigation actions: the map-setup dance as declarative GOAP
operators. Every action is an idempotent ensure (set a predicate to its target
value, never a blind toggle) so planning on ``unknown`` is safe; every execute
reuses an existing helper and touches only pure-read / reversible-navigation
UI -- never a tap that commits a game action, and never a map cell (紅線).

The pinch/zoom orchestration reuses the same ``pinch`` primitives the legacy
controller's ``_zoom_to_max`` drives (pinch.zoom_out_max / pick_pinch_center /
zoom_out_fingers + vision.zoom_at_max); the flow keeps its own thin orchestration
because its failure semantics differ (a flow action returns False and lets the
tick loop decide, it does not release the grid or raise SurveyIncomplete -- that
is the macro layer's job in Round 2.1). The legacy controller is left untouched.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from ...actuation import pinch
from ...goap.action import Action
from .. import map_view, vision
from .. import settings as battle_settings
from . import vocabulary as V

log = logging.getLogger(__name__)


@dataclass
class FlowContext:
    """Everything a flow action needs to run against the device (or a fake).
    ``frame`` is the tick's already-captured frame an action may reuse instead
    of re-capturing; ``log`` mirrors CoverageScanSource.ledger_log
    (``log(kind, **data)``) and may be None; ``sleep``/``detect``/``pincher``/
    ``keyguard`` are injectable seams so the whole layer is offline-testable."""

    perception: object
    actuator: object
    frame: object = None
    pincher: object | None = None
    keyguard: object | None = None
    log: Callable[..., None] | None = None
    sleep: Callable[[float], None] = time.sleep
    detect: Callable[..., list] | None = None

    def _frame(self):
        return self.frame if self.frame is not None else self.perception.capture()

    def emit(self, kind: str, **data) -> None:
        if self.log is not None:
            self.log(kind, **data)


def detect_unit_peaks(frame) -> list[tuple[int, int]]:
    """Unit peaks for the empty-land dismiss tap's clearance math, unioned over
    the arc + density detectors (mirrors the legacy controller's _pinch_peaks:
    a wrong-domain detector only contributes phantom peaks that nudge the tap,
    never a unit tap). Each detector is guarded; a raise contributes nothing."""
    peaks: list[tuple[int, int]] = []
    for detect in (
        vision.find_unit_density_peaks,
        vision.find_enemy_units,
        vision.find_ally_units,
        vision.find_third_party_units,
    ):
        try:
            peaks.extend((int(x), int(y)) for x, y in detect(frame))
        except Exception:
            continue
    return peaks


class ReachHub(Action):
    """Cancel back to the our-turn hub (map_view.return_to_top)."""

    name = "reach_hub"
    cost = 1.0
    preconditions = {V.OBSTRUCTION: V.OBSTRUCTION_NONE}
    effects = {V.VIEW: V.VIEW_HUB}

    def execute(self, ctx: FlowContext) -> bool:
        return map_view.return_to_top(
            ctx.perception, ctx.actuator, keyguard=ctx.keyguard, sleep=ctx.sleep
        )


class ClearObstruction(Action):
    """Close a 單位設置詳情 modal (map_view.clear_obstruction, detect=None -- the
    modal-only single source of truth)."""

    name = "clear_obstruction"
    cost = 1.0
    preconditions = {V.OBSTRUCTION: V.OBSTRUCTION_MODAL}
    effects = {V.OBSTRUCTION: V.OBSTRUCTION_NONE}

    def execute(self, ctx: FlowContext) -> bool:
        on_close = (lambda f: ctx.emit("scan_modal_closed", frame=f)) if ctx.log else None
        map_view.clear_obstruction(
            ctx.perception, ctx.actuator, ctx._frame(), sleep=ctx.sleep, on_close=on_close
        )
        return True


class ClearSelectionResidue(Action):
    """Dismiss a docked enemy-selection 比較 HUD by tapping empty land (R1.7
    chain via map_view.clear_obstruction with a unit detector)."""

    name = "clear_selection_residue"
    cost = 1.0
    preconditions = {V.OBSTRUCTION: V.OBSTRUCTION_SELECTION}
    effects = {V.OBSTRUCTION: V.OBSTRUCTION_NONE}

    def execute(self, ctx: FlowContext) -> bool:
        detect = ctx.detect if ctx.detect is not None else detect_unit_peaks
        on_clear = (
            (lambda f, tap, attempt: ctx.emit("scan_selection_cleared", tap=tap, attempt=attempt))
            if ctx.log
            else None
        )
        try:
            map_view.clear_obstruction(
                ctx.perception,
                ctx.actuator,
                ctx._frame(),
                sleep=ctx.sleep,
                detect=detect,
                on_clear_selection=on_clear,
            )
        except map_view.SelectionResidueStuck:
            return False
        return True


class ExpandUnitList(Action):
    """Open the 可行動單位 card strip (map_view.expand_unit_list)."""

    name = "expand_unit_list"
    cost = 1.0
    preconditions = {V.OBSTRUCTION: V.OBSTRUCTION_NONE}
    effects = {V.UNIT_LIST: V.UNIT_LIST_EXPANDED}

    def execute(self, ctx: FlowContext) -> bool:
        return map_view.expand_unit_list(ctx.perception, ctx.actuator, sleep=ctx.sleep)


class CollapseUnitList(Action):
    """Collapse the 可行動單位 card strip for the widest map
    (map_view.collapse_unit_list)."""

    name = "collapse_unit_list"
    cost = 1.0
    preconditions = {V.OBSTRUCTION: V.OBSTRUCTION_NONE}
    effects = {V.UNIT_LIST: V.UNIT_LIST_COLLAPSED}

    def execute(self, ctx: FlowContext) -> bool:
        return map_view.collapse_unit_list(ctx.perception, ctx.actuator, sleep=ctx.sleep)


class EnableGrid(Action):
    """Drive 顯示方格 on (battle_settings.set_battle_grid, True)."""

    name = "enable_grid"
    cost = 1.0
    preconditions = {V.VIEW: V.VIEW_HUB, V.OBSTRUCTION: V.OBSTRUCTION_NONE}
    effects = {V.GRID: V.GRID_ON}

    def execute(self, ctx: FlowContext) -> bool:
        return battle_settings.set_battle_grid(
            ctx.perception.capture, ctx.actuator.tap, True, sleep=ctx.sleep
        )


class DisableGrid(Action):
    """Drive 顯示方格 off (battle_settings.set_battle_grid, False)."""

    name = "disable_grid"
    cost = 1.0
    preconditions = {V.VIEW: V.VIEW_HUB, V.OBSTRUCTION: V.OBSTRUCTION_NONE}
    effects = {V.GRID: V.GRID_OFF}

    def execute(self, ctx: FlowContext) -> bool:
        return battle_settings.set_battle_grid(
            ctx.perception.capture, ctx.actuator.tap, False, sleep=ctx.sleep
        )


class ZoomToMax(Action):
    """Pinch the battle camera to its furthest zoom-out and verify it with
    vision.zoom_at_max. Needs the grid on (a lattice to verify against)."""

    name = "zoom_to_max"
    cost = 1.0
    preconditions = {V.VIEW: V.VIEW_HUB, V.OBSTRUCTION: V.OBSTRUCTION_NONE, V.GRID: V.GRID_ON}
    effects = {V.ZOOM: V.ZOOM_MAX}

    def execute(self, ctx: FlowContext) -> bool:
        return zoom_to_max(ctx)


def zoom_to_max(ctx: FlowContext) -> bool:
    """Pinch-verify the camera to max zoom, reusing the pinch primitives. Returns
    whether vision.zoom_at_max confirmed after at most two passes. Fail-soft
    (False, no raise) -- the tick loop owns what a failed zoom means."""
    pincher = ctx.pincher
    if pincher is None:
        log.warning("no pincher in flow context; cannot zoom to max")
        return False

    state = {"frame": ctx._frame()}

    def capture():
        f = ctx.perception.capture()
        state["frame"] = f
        return f

    def clear(frame):
        on_close = (lambda fr: ctx.emit("scan_modal_closed", frame=fr)) if ctx.log else None
        return map_view.clear_obstruction(
            ctx.perception, ctx.actuator, frame, sleep=ctx.sleep, on_close=on_close
        )

    def pinch_step():
        base = state["frame"]
        center = (
            pinch.pick_pinch_center(detect_unit_peaks(base))
            if base is not None
            else pinch.PINCH_CENTER_DEFAULT
        )
        pincher.pinch(*pinch.zoom_out_fingers(center=center))

    def on_step(step: pinch.PitchStep) -> None:
        ctx.emit(
            "zoom_step",
            index=step.index,
            col_pitch=step.col_pitch,
            row_pitch=step.row_pitch,
            change=step.change,
            source=step.source,
        )

    def zoom_pass():
        pinch.zoom_out_max(
            capture=capture,
            pinch_step=pinch_step,
            obstruction=clear,
            on_step=on_step,
            sleep=ctx.sleep,
        )
        return clear(ctx.perception.capture())

    frame = zoom_pass()
    if vision.zoom_at_max(frame) is True:
        return True
    log.warning("flow zoom not confirmed at max after the first pass; pinching once more")
    frame = zoom_pass()
    return vision.zoom_at_max(frame) is True


# the repair / navigation catalog. Structurally pure-read / reversible only:
# nothing here commits a game action or taps a map cell (紅線). The macro /
# content actions (Round 2.1) extend this list.
REPAIR_NAV_ACTIONS: tuple[Action, ...] = (
    ReachHub(),
    ClearObstruction(),
    ClearSelectionResidue(),
    ExpandUnitList(),
    CollapseUnitList(),
    EnableGrid(),
    DisableGrid(),
    ZoomToMax(),
)
