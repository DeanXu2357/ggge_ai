"""Offline tests for battle.flow.controller2.BattleController2: the tick loop.
Integration cases drive the REAL repair/navigation catalog over a fake world
(the action helpers are monkeypatched to mutate a dict the translator reads);
branch cases use synthetic actions to pin the continue-vs-replan rule exactly.
No device."""

from __future__ import annotations

from ggge_ai.battle.flow import actions as flow_actions
from ggge_ai.battle.flow import vocabulary as V
from ggge_ai.battle.flow.actions import REPAIR_NAV_ACTIONS
from ggge_ai.battle.flow.controller2 import BattleController2, FlowConfig
from ggge_ai.goap.action import Action, Goal
from ggge_ai.goap.state import WorldState

NOOP = lambda *a, **k: None  # noqa: E731

SCAN_READY = {
    V.VIEW: V.VIEW_HUB,
    V.OBSTRUCTION: V.OBSTRUCTION_NONE,
    V.UNIT_LIST: V.UNIT_LIST_COLLAPSED,
    V.GRID: V.GRID_ON,
    V.ZOOM: V.ZOOM_MAX,
}


class _Perception:
    def capture(self):
        return object()

    def probe(self, ids, frame=None):
        return {}


class _Actuator:
    def tap(self, x, y):
        pass


def _scan_goal():
    g = Goal()
    g.name = "scan_ready"
    g.conditions = dict(SCAN_READY)
    return g


def _translator_of(world):
    def translate(frame, probe, prog):
        return WorldState({**world, **(prog or {})})

    return translate


def _controller(world, *, actions, events, diag_save=None, config=None):
    return BattleController2(
        _Perception(),
        _Actuator(),
        actions=actions,
        translator=_translator_of(world),
        ledger_log=lambda kind, **d: events.append((kind, d)),
        diag_save=diag_save,
        config=config,
        sleep=NOOP,
    )


def _kinds(events):
    return [k for k, _ in events]


# --- happy path -------------------------------------------------------------


def test_happy_path_matches_scout_prefix_order(monkeypatch):
    """A clean cold hub: the plan and the helper call sequence match the legacy
    _scout precondition -- collapse the list, turn the grid on, zoom to max."""
    world = {
        V.VIEW: V.VIEW_HUB,
        V.OBSTRUCTION: V.OBSTRUCTION_NONE,
        V.UNIT_LIST: V.UNIT_LIST_EXPANDED,
        V.GRID: V.GRID_OFF,
        V.ZOOM: V.UNKNOWN,
    }
    calls = []

    def collapse(perc, act, **kw):
        calls.append("collapse")
        world[V.UNIT_LIST] = V.UNIT_LIST_COLLAPSED
        return True

    def set_grid(cap, tap, desired, **kw):
        calls.append(("grid", desired))
        world[V.GRID] = V.GRID_ON if desired else V.GRID_OFF
        return True

    def zoom(ctx):
        calls.append("zoom")
        world[V.ZOOM] = V.ZOOM_MAX
        return True

    monkeypatch.setattr(flow_actions.map_view, "collapse_unit_list", collapse)
    monkeypatch.setattr(flow_actions.battle_settings, "set_battle_grid", set_grid)
    monkeypatch.setattr(flow_actions, "zoom_to_max", zoom)

    events = []
    ok = _controller(world, actions=list(REPAIR_NAV_ACTIONS), events=events).run(_scan_goal())

    assert ok is True
    assert calls == ["collapse", ("grid", True), "zoom"]
    plans = [d["plan"] for k, d in events if k == "flow_plan"]
    assert plans[0] == ["collapse_unit_list", "enable_grid", "zoom_to_max"]


def test_goal_already_satisfied_does_nothing(monkeypatch):
    world = dict(SCAN_READY)
    called = []
    monkeypatch.setattr(
        flow_actions.battle_settings,
        "set_battle_grid",
        lambda *a, **k: called.append("grid") or True,
    )
    events = []
    ok = _controller(world, actions=list(REPAIR_NAV_ACTIONS), events=events).run(_scan_goal())
    assert ok is True
    assert called == []
    assert "flow_plan" not in _kinds(events)  # never even planned


def test_idempotent_ensure_skips_satisfied_predicate_at_planning(monkeypatch):
    # unit_list already collapsed: the plan contains only enable_grid, never a
    # redundant collapse. Ensure semantics = the planner drops satisfied keys.
    world = {
        V.VIEW: V.VIEW_HUB,
        V.OBSTRUCTION: V.OBSTRUCTION_NONE,
        V.UNIT_LIST: V.UNIT_LIST_COLLAPSED,
        V.GRID: V.GRID_OFF,
        V.ZOOM: V.UNKNOWN,
    }
    calls = []
    monkeypatch.setattr(
        flow_actions.map_view,
        "collapse_unit_list",
        lambda perc, act, **kw: calls.append("collapse") or True,
    )
    monkeypatch.setattr(
        flow_actions.battle_settings,
        "set_battle_grid",
        lambda cap, tap, desired, **kw: (world.__setitem__(V.GRID, V.GRID_ON), True)[1],
    )
    goal = Goal()
    goal.conditions = {V.UNIT_LIST: V.UNIT_LIST_COLLAPSED, V.GRID: V.GRID_ON}
    events = []
    ok = _controller(world, actions=list(REPAIR_NAV_ACTIONS), events=events).run(goal)
    assert ok is True
    assert calls == []  # collapse never ran: it was already satisfied
    plans = [d["plan"] for k, d in events if k == "flow_plan"]
    assert plans[0] == ["enable_grid"]


# --- modal injection: replan through ClearObstruction -----------------------


def test_modal_injected_midrun_replans_through_clear_obstruction(monkeypatch):
    world = {
        V.VIEW: V.VIEW_HUB,
        V.OBSTRUCTION: V.OBSTRUCTION_NONE,
        V.UNIT_LIST: V.UNIT_LIST_COLLAPSED,
        V.GRID: V.GRID_OFF,
        V.ZOOM: V.UNKNOWN,
    }
    calls = []
    injected = {"done": False}

    def set_grid(cap, tap, desired, **kw):
        calls.append(("grid", desired))
        world[V.GRID] = V.GRID_ON if desired else V.GRID_OFF
        if desired and not injected["done"]:
            injected["done"] = True  # a stray tap opened a modal over the map
            world.update(
                {
                    V.VIEW: "modal",
                    V.OBSTRUCTION: V.OBSTRUCTION_MODAL,
                    V.UNIT_LIST: V.UNKNOWN,
                    V.GRID: V.UNKNOWN,
                    V.ZOOM: V.UNKNOWN,
                }
            )
        return True

    def clear(perc, act, frame, **kw):
        assert kw.get("detect") is None  # modal-only leg
        calls.append("clear_obstruction")
        world.update(
            {
                V.VIEW: V.VIEW_HUB,
                V.OBSTRUCTION: V.OBSTRUCTION_NONE,
                V.UNIT_LIST: V.UNIT_LIST_COLLAPSED,
                V.GRID: V.GRID_ON,  # the toggle was really on under the modal
            }
        )
        return frame

    monkeypatch.setattr(flow_actions.battle_settings, "set_battle_grid", set_grid)
    monkeypatch.setattr(flow_actions.map_view, "clear_obstruction", clear)
    monkeypatch.setattr(
        flow_actions.map_view, "return_to_top", lambda perc, act, **kw: calls.append("hub") or True
    )
    monkeypatch.setattr(
        flow_actions.map_view,
        "collapse_unit_list",
        lambda perc, act, **kw: calls.append("collapse") or True,
    )
    monkeypatch.setattr(
        flow_actions,
        "zoom_to_max",
        lambda ctx: (calls.append("zoom"), world.__setitem__(V.ZOOM, V.ZOOM_MAX), True)[-1],
    )

    events = []
    ok = _controller(world, actions=list(REPAIR_NAV_ACTIONS), events=events).run(_scan_goal())

    assert ok is True
    assert "clear_obstruction" in calls  # the modal was cleared by ClearObstruction
    assert "unplanned_transition" in _kinds(events)
    plans = [d for k, d in events if k == "flow_plan"]
    assert len(plans) >= 2  # replan happened
    # the modal was cleared before the eventual zoom
    assert calls.index("clear_obstruction") < calls.index("zoom")


# --- selection residue: replan through ClearSelectionResidue ----------------


def test_selection_residue_injected_replans_through_clear_selection(monkeypatch):
    world = {
        V.VIEW: V.VIEW_HUB,
        V.OBSTRUCTION: V.OBSTRUCTION_NONE,
        V.UNIT_LIST: V.UNIT_LIST_EXPANDED,
        V.GRID: V.GRID_OFF,
        V.ZOOM: V.UNKNOWN,
    }
    calls = []
    injected = {"done": False}

    def collapse(perc, act, **kw):
        calls.append("collapse")
        world[V.UNIT_LIST] = V.UNIT_LIST_COLLAPSED
        if not injected["done"]:
            injected["done"] = True  # a stray tap docked the enemy-selection HUD
            world[V.OBSTRUCTION] = V.OBSTRUCTION_SELECTION
        return True

    def clear(perc, act, frame, **kw):
        # residue leg supplies a unit detector; it clears the docked HUD
        assert kw.get("detect") is not None
        calls.append("clear_selection_residue")
        world[V.OBSTRUCTION] = V.OBSTRUCTION_NONE
        return frame

    monkeypatch.setattr(flow_actions.map_view, "collapse_unit_list", collapse)
    monkeypatch.setattr(flow_actions.map_view, "clear_obstruction", clear)
    monkeypatch.setattr(
        flow_actions.battle_settings,
        "set_battle_grid",
        lambda cap, tap, desired, **kw: (world.__setitem__(V.GRID, V.GRID_ON), True)[1],
    )
    monkeypatch.setattr(
        flow_actions,
        "zoom_to_max",
        lambda ctx: (world.__setitem__(V.ZOOM, V.ZOOM_MAX), True)[1],
    )

    events = []
    ok = _controller(world, actions=list(REPAIR_NAV_ACTIONS), events=events).run(_scan_goal())

    assert ok is True
    assert "clear_selection_residue" in calls
    plans = [d for k, d in events if k == "flow_plan"]
    assert len(plans) >= 2  # the residue forced a replan


# --- unplanned_transition: continue-vs-replan branch ------------------------


def _fake_action(name, pre, eff, run):
    a = Action()
    a.name = name
    a.preconditions = pre
    a.effects = eff
    a.cost = 1.0
    a.execute = run
    return a


def test_unplanned_diff_off_the_remaining_plan_keeps_going(monkeypatch):
    # an unplanned change touching only a key the rest of the plan (and goal)
    # does not depend on: log it, but keep executing the SAME plan (no replan).
    world = {"ready": "no", "done": "no"}

    def prepare(ctx):
        world["noise"] = "x"  # changed something irrelevant, NOT ready
        return True

    def set_done(ctx):
        world["done"] = "yes"
        return True

    a_prepare = _fake_action("prepare", {}, {"ready": "yes"}, prepare)
    a_done = _fake_action("set_done", {"ready": "yes"}, {"done": "yes"}, set_done)
    goal = Goal()
    goal.conditions = {"done": "yes"}

    events = []
    ok = _controller(world, actions=[a_prepare, a_done], events=events).run(goal)

    assert ok is True
    assert "unplanned_transition" in _kinds(events)
    assert _kinds(events).count("flow_plan") == 1  # no replan: same plan continued


def test_unplanned_diff_hitting_the_remaining_plan_replans(monkeypatch):
    # the change lands on a key the next step depends on (its precondition):
    # discard the plan and replan.
    world = {"ready": "no", "done": "no"}
    step = {"n": 0}

    def prepare(ctx):
        step["n"] += 1
        # first run corrupts ready (a remaining-plan dependency); second run fixes it
        world["ready"] = "yes" if step["n"] >= 2 else "wrong"
        return True

    def set_done(ctx):
        world["done"] = "yes"
        return True

    a_prepare = _fake_action("prepare", {}, {"ready": "yes"}, prepare)
    a_done = _fake_action("set_done", {"ready": "yes"}, {"done": "yes"}, set_done)
    goal = Goal()
    goal.conditions = {"done": "yes"}

    events = []
    ok = _controller(world, actions=[a_prepare, a_done], events=events).run(goal)

    assert ok is True
    assert "unplanned_transition" in _kinds(events)
    assert _kinds(events).count("flow_plan") >= 2  # replanned after the dep was hit


def test_no_progress_action_fails_loud_after_bound(monkeypatch):
    # an action that never moves the world is retried up to the bound, then the
    # loop aborts loudly rather than spinning forever.
    world = {"done": "no"}

    def stuck(ctx):
        return True  # claims success but changes nothing

    a_stuck = _fake_action("stuck", {}, {"done": "yes"}, stuck)
    goal = Goal()
    goal.conditions = {"done": "yes"}

    events = []
    config = FlowConfig(max_consecutive_failures=3)
    ok = _controller(world, actions=[a_stuck], events=events, config=config).run(goal)

    assert ok is False
    aborts = [d for k, d in events if k == "flow_abort"]
    assert aborts and aborts[-1]["reason"] == "stuck"


# --- unknown handling -------------------------------------------------------


def test_view_unknown_waits_then_aborts_with_diag(monkeypatch):
    world = {
        V.VIEW: V.UNKNOWN,
        V.OBSTRUCTION: V.OBSTRUCTION_NONE,
        V.UNIT_LIST: V.UNKNOWN,
        V.GRID: V.UNKNOWN,
        V.ZOOM: V.UNKNOWN,
    }
    saved = []

    def diag_save(frame, tag):
        saved.append(tag)
        return f"diag/{tag}.png"

    events = []
    config = FlowConfig(max_unknown_waits=2, diag_every=1)
    ok = _controller(
        world, actions=list(REPAIR_NAV_ACTIONS), events=events, diag_save=diag_save, config=config
    ).run(_scan_goal())

    assert ok is False
    assert len(saved) == 2  # diag stashed on each wait before the timeout
    unknown_events = [d for k, d in events if k == "flow_unknown"]
    assert len(unknown_events) == 2
    assert unknown_events[0]["frame_path"] == "diag/flow_unknown_1.png"
    aborts = [d for k, d in events if k == "flow_abort"]
    assert aborts and aborts[-1]["reason"] == "view_unknown_timeout"


def test_unknown_frame_with_clearable_obstruction_does_not_wait(monkeypatch):
    # a modal that also reads view=unknown must REPLAN to clear, not wait it out
    # (the wait path is only for genuinely opaque frames).
    world = {
        V.VIEW: V.UNKNOWN,
        V.OBSTRUCTION: V.OBSTRUCTION_MODAL,
        V.UNIT_LIST: V.UNKNOWN,
        V.GRID: V.UNKNOWN,
        V.ZOOM: V.UNKNOWN,
    }
    cleared = []

    def clear(perc, act, frame, **kw):
        cleared.append("clear")
        world.update({V.VIEW: V.VIEW_HUB, V.OBSTRUCTION: V.OBSTRUCTION_NONE})
        return frame

    monkeypatch.setattr(flow_actions.map_view, "clear_obstruction", clear)
    monkeypatch.setattr(
        flow_actions.map_view, "return_to_top", lambda perc, act, **kw: True
    )
    monkeypatch.setattr(
        flow_actions.battle_settings,
        "set_battle_grid",
        lambda cap, tap, desired, **kw: (world.__setitem__(V.GRID, V.GRID_ON), True)[1],
    )
    monkeypatch.setattr(
        flow_actions.map_view,
        "collapse_unit_list",
        lambda perc, act, **kw: (world.__setitem__(V.UNIT_LIST, V.UNIT_LIST_COLLAPSED), True)[1],
    )
    monkeypatch.setattr(
        flow_actions,
        "zoom_to_max",
        lambda ctx: (world.__setitem__(V.ZOOM, V.ZOOM_MAX), True)[1],
    )

    events = []
    ok = _controller(world, actions=list(REPAIR_NAV_ACTIONS), events=events).run(_scan_goal())

    assert ok is True
    assert cleared == ["clear"]  # it planned+cleared instead of waiting
    assert "flow_unknown" not in _kinds(events)  # never entered the wait path


# --- PlanNotFound -----------------------------------------------------------


def test_plan_not_found_aborts_with_state_dump():
    # a goal predicate no action can reach: honest abort + state dump, never a
    # blind retry spin.
    world = dict(SCAN_READY)
    goal = Goal()
    goal.conditions = {"sim_synced": True}  # no repair/nav action provides this

    events = []
    ok = _controller(world, actions=list(REPAIR_NAV_ACTIONS), events=events).run(goal)

    assert ok is False
    aborts = [d for k, d in events if k == "flow_abort"]
    assert aborts and aborts[-1]["reason"] == "plan_not_found"
    assert "state" in aborts[-1]  # the state dump rode along
