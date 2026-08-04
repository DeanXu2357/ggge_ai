"""Offline tests for battle.map_view: view recognition and backing out to the
top-level hub. Perception/actuator are fakes; the vision pixel readers are
stubbed. No device."""

from __future__ import annotations

import pytest

from ggge_ai.battle import map_view


class Box:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h


class El:
    def __init__(self, confidence, bbox=None):
        self.confidence = confidence
        self.bbox = bbox


_LABEL = {
    "hub": map_view.HUB_LABEL,
    "unit_move": "label_unit_move",
    "weapon_select": "label_weapon_select",
}


class FakePerception:
    """Serves a scripted sequence of views; a cancel tap advances to the next."""

    def __init__(self, views):
        self.views = views
        self.i = 0
        self.modal = False
        self.cards = False
        self.settings = False
        self.selection = False
        self.list_state = "collapsed"

    @property
    def view(self):
        return self.views[min(self.i, len(self.views) - 1)]

    def capture(self):
        return object()

    def probe(self, ids, frame=None):
        out = {}
        if map_view.RETURN_BUTTON in ids and self.view != "hub":
            out[map_view.RETURN_BUTTON] = El(0.9, Box(1690, 870, 230, 210))
        label = _LABEL.get(self.view)
        for i in ids:
            if i == label:
                out[i] = El(0.9)
        return out


class FakeActuator:
    def __init__(self, perception):
        self.perception = perception
        self.taps = []

    def tap(self, x, y):
        self.taps.append((x, y))
        if self.perception.i < len(self.perception.views) - 1:
            self.perception.i += 1
        if self.perception.modal:  # a close tap clears the modal
            self.perception.modal = False
            _CUR["modal"] = False


def _fake_unit_list_state(_frame):
    # mirrors vision.unit_list_state: a covering modal is "unknown", never a
    # collapsed/expanded answer
    if _CUR["modal"]:
        return map_view.vision.UNIT_LIST_UNKNOWN
    return _CUR["list_state"]


@pytest.fixture(autouse=True)
def _stub_vision(monkeypatch):
    # classify_view / collapse consult these; drive them off the fake
    monkeypatch.setattr(map_view.vision, "is_unit_detail_modal", lambda f: _CUR["modal"])
    monkeypatch.setattr(map_view.vision, "unit_cards_present", lambda f: _CUR["cards"])
    monkeypatch.setattr(map_view.vision, "unit_list_state", _fake_unit_list_state)
    monkeypatch.setattr(map_view.vision, "enemy_selection_active", lambda f: _CUR["selection"])
    monkeypatch.setattr(map_view.settings, "is_battle_tab_selected", lambda f: _CUR["settings"])
    yield


_CUR = {
    "modal": False, "cards": False, "settings": False,
    "selection": False, "list_state": "collapsed",
}


def _bind(perc):
    _CUR["modal"] = perc.modal
    _CUR["cards"] = perc.cards
    _CUR["settings"] = perc.settings
    _CUR["selection"] = perc.selection
    _CUR["list_state"] = perc.list_state


def test_classify_hub():
    p = FakePerception(["hub"])
    _bind(p)
    assert map_view.classify_view(p) == "hub"
    assert map_view.is_top_hub(p) is True


def test_classify_substate_and_unknown():
    p = FakePerception(["unit_move"])
    _bind(p)
    assert map_view.classify_view(p) == "unit_move"
    p2 = FakePerception(["enemy"])  # no label matches -> unknown
    _bind(p2)
    assert map_view.classify_view(p2) == "unknown"


def test_classify_modal_wins():
    p = FakePerception(["unit_move"])
    p.modal = True
    _bind(p)
    assert map_view.classify_view(p) == "modal"


def test_classify_settings():
    p = FakePerception(["enemy"])  # settings page has no battle label
    p.settings = True
    _bind(p)
    assert map_view.classify_view(p) == "settings"


def test_classify_modal_beats_settings():
    # both page predicates fire; the modal veto is ordered first and wins
    p = FakePerception(["enemy"])
    p.modal = True
    p.settings = True
    _bind(p)
    assert map_view.classify_view(p) == "modal"


def test_return_to_top_cancels_substate_via_return_button():
    p = FakePerception(["unit_move", "hub"])
    _bind(p)
    a = FakeActuator(p)
    assert map_view.return_to_top(p, a, sleep=lambda s: None) is True
    # the one tap was the 返回 button center (region 1690,870,230,210)
    assert a.taps == [(1805, 975)]


def test_return_to_top_closes_modal_then_reaches_hub():
    p = FakePerception(["hub"])  # underlying view is hub, but a modal covers it
    p.modal = True
    _bind(p)
    a = FakeActuator(p)
    assert map_view.return_to_top(p, a, sleep=lambda s: None) is True
    assert a.taps[0] == map_view.UNIT_DETAIL_CLOSE


def test_return_to_top_gives_up_soft_when_never_hub():
    p = FakePerception(["unit_move"])  # never advances to hub
    _bind(p)
    a = FakeActuator(p)
    # single-view script: taps do not advance past it, so hub never reached
    assert map_view.return_to_top(p, a, sleep=lambda s: None, attempts=3) is False


def test_clear_obstruction_closes_modal_recaptures_and_logs():
    # single source of truth: a modal frame is closed (tap 關閉), the pre-close
    # frame reaches on_close, and a fresh capture comes back
    p = FakePerception(["hub"])
    p.modal = True
    _bind(p)
    a = FakeActuator(p)
    logged = []
    frame = object()
    out = map_view.clear_obstruction(
        p, a, frame, sleep=lambda s: None, on_close=lambda f: logged.append(f)
    )
    assert a.taps == [map_view.UNIT_DETAIL_CLOSE]
    assert logged == [frame]
    assert out is not frame  # recaptured after the close


def test_clear_obstruction_passes_through_without_modal():
    p = FakePerception(["hub"])
    p.modal = False
    _bind(p)
    a = FakeActuator(p)
    frame = object()
    out = map_view.clear_obstruction(p, a, frame, sleep=lambda s: None)
    assert a.taps == []
    assert out is frame  # same frame, no recapture




def test_clear_obstruction_dismisses_selection_residue_with_empty_land_tap():
    # 輪七: a docked enemy-selection 比較 HUD is cleared by tapping empty land
    # (max-min clearance from the detected units), then verified gone. Only the
    # scan path (detect given) runs this leg.
    p = FakePerception(["hub"])
    p.selection = True
    _bind(p)
    a = FakeActuator(p)
    peaks = [(300.0, 300.0), (1600.0, 600.0)]

    def tap(x, y):
        a.taps.append((x, y))
        _CUR["selection"] = False  # an empty-land tap deselects

    a.tap = tap
    frame = object()
    out = map_view.clear_obstruction(
        p, a, frame, sleep=lambda s: None, detect=lambda f: peaks
    )
    assert len(a.taps) == 1
    tx, ty = a.taps[0]
    # the dismiss tap landed clear of every detected unit (紅線: never a unit tap)
    assert min(((tx - px) ** 2 + (ty - py) ** 2) ** 0.5 for px, py in peaks) > 150
    assert _CUR["selection"] is False
    assert out is not frame  # recaptured after the dismiss


def test_clear_obstruction_fails_loud_when_residue_will_not_dismiss():
    # fail-loud: the tap never clears the HUD, so after the initial attempt plus
    # one retry the chain raises rather than trusting a poisoned frame.
    p = FakePerception(["hub"])
    p.selection = True
    _bind(p)
    a = FakeActuator(p)
    a.tap = lambda x, y: a.taps.append((x, y))  # tap does NOT dismiss

    with pytest.raises(map_view.SelectionResidueStuck):
        map_view.clear_obstruction(
            p, a, object(), sleep=lambda s: None, detect=lambda f: []
        )
    assert len(a.taps) == 2  # initial + one retry, then loud


def test_clear_obstruction_ignores_selection_residue_without_detect():
    # the three non-scan callers pass no detect: the residue leg is skipped and
    # a residue frame passes through untouched (modal-only behaviour unchanged).
    p = FakePerception(["hub"])
    p.selection = True
    _bind(p)
    a = FakeActuator(p)
    frame = object()
    out = map_view.clear_obstruction(p, a, frame, sleep=lambda s: None)
    assert a.taps == []
    assert out is frame


def test_clear_obstruction_chains_modal_then_selection():
    # both present on the scan path: the modal is closed first, then the residue
    # dismissed, in one call.
    p = FakePerception(["hub"])
    p.modal = True
    p.selection = True
    _bind(p)
    a = FakeActuator(p)

    def tap(x, y):
        a.taps.append((x, y))
        if (x, y) == map_view.UNIT_DETAIL_CLOSE:
            _CUR["modal"] = False
        else:
            _CUR["selection"] = False

    a.tap = tap
    map_view.clear_obstruction(
        p, a, object(), sleep=lambda s: None, detect=lambda f: []
    )
    assert a.taps[0] == map_view.UNIT_DETAIL_CLOSE  # modal closed first
    assert len(a.taps) == 2  # then one empty-land dismiss
    assert _CUR["modal"] is False and _CUR["selection"] is False


def test_collapse_unit_list_returns_true_when_already_collapsed():
    p = FakePerception(["hub"])
    p.list_state = "collapsed"
    _bind(p)
    a = FakeActuator(p)
    assert map_view.collapse_unit_list(p, a, sleep=lambda s: None) is True
    assert a.taps == []  # already collapsed: no toggle tap


def test_collapse_unit_list_taps_toggle_when_expanded():
    p = FakePerception(["hub"])
    p.list_state = "expanded"
    _bind(p)
    a = FakeActuator(p)

    def tap(x, y):
        a.taps.append((x, y))
        if (x, y) == map_view.UNIT_LIST_COLLAPSE:
            _CUR["list_state"] = "collapsed"

    a.tap = tap
    assert map_view.collapse_unit_list(p, a, sleep=lambda s: None) is True
    assert map_view.UNIT_LIST_COLLAPSE in a.taps


def test_collapse_unit_list_rejects_modal_as_collapsed():
    # 07-23 輪四 map_view-level regression: a modal covers the strip, so
    # unit_cards_present reads False -- which the old `not unit_cards_present`
    # accepted as collapsed and returned True. "unknown" is not "collapsed":
    # clear the obstruction, and never report success on a covered strip.
    p = FakePerception(["hub"])
    p.modal = True
    p.list_state = "expanded"  # the real list, behind the modal, is open
    _bind(p)
    a = FakeActuator(p)
    assert map_view.collapse_unit_list(p, a, sleep=lambda s: None) is False
    assert map_view.UNIT_DETAIL_CLOSE in a.taps  # cleared the modal first


def test_expand_unit_list_returns_true_when_already_expanded():
    p = FakePerception(["hub"])
    p.list_state = "expanded"
    _bind(p)
    a = FakeActuator(p)
    assert map_view.expand_unit_list(p, a, sleep=lambda s: None) is True
    assert a.taps == []  # already expanded: no toggle tap


def test_expand_unit_list_taps_expand_toggle_when_collapsed():
    # the mirror of collapse: from a positively-read collapsed strip, tap the ▲
    # expand toggle (never the ▽ collapse one) to open it.
    p = FakePerception(["hub"])
    p.list_state = "collapsed"
    _bind(p)
    a = FakeActuator(p)

    def tap(x, y):
        a.taps.append((x, y))
        if (x, y) == map_view.UNIT_LIST_EXPAND:
            _CUR["list_state"] = "expanded"

    a.tap = tap
    assert map_view.expand_unit_list(p, a, sleep=lambda s: None) is True
    assert map_view.UNIT_LIST_EXPAND in a.taps
    assert map_view.UNIT_LIST_COLLAPSE not in a.taps


def test_expand_unit_list_rejects_modal_as_expanded():
    # three-valued: a covering modal reads "unknown", never accepted as the
    # target; the obstruction is cleared before any conclusion.
    p = FakePerception(["hub"])
    p.modal = True
    p.list_state = "collapsed"
    _bind(p)
    a = FakeActuator(p)
    assert map_view.expand_unit_list(p, a, sleep=lambda s: None) is False
    assert map_view.UNIT_DETAIL_CLOSE in a.taps  # cleared the modal first


def test_ensure_max_view_reaches_hub_and_collapses_list():
    p = FakePerception(["unit_move", "hub"])
    p.list_state = "expanded"
    _bind(p)
    a = FakeActuator(p)

    def tap(x, y):
        a.taps.append((x, y))
        if p.i < len(p.views) - 1:
            p.i += 1
        if (x, y) == map_view.UNIT_LIST_COLLAPSE:
            _CUR["list_state"] = "collapsed"

    a.tap = tap
    assert map_view.ensure_max_view(p, a, sleep=lambda s: None) is True
    assert map_view.UNIT_LIST_COLLAPSE in a.taps


class _NoButtonPerception(FakePerception):
    """A frame where the 返回 button is not visible, so return_to_top must
    choose between the neutral nudge and (strict mode) touching nothing."""

    def probe(self, ids, frame=None):
        out = super().probe(ids, frame)
        out.pop(map_view.RETURN_BUTTON, None)
        return out


def test_return_to_top_strict_mode_skips_the_neutral_nudge():
    # Round 1.5 escape red line: on an unknown frame with no 返回 button the
    # default mode neutral-nudges (1170,90); strict mode must touch NOTHING --
    # a map tap in unit-move mode would commit a move.
    p = _NoButtonPerception(["enemy"])  # no label matches -> unknown, no button
    _bind(p)
    a = FakeActuator(p)
    reached = map_view.return_to_top(
        p, a, sleep=lambda s: None, attempts=2, allow_neutral_nudge=False
    )
    assert reached is False
    assert a.taps == []  # never a neutral nudge, never a map cell


def test_return_to_top_default_mode_neutral_nudges_when_no_button():
    p = _NoButtonPerception(["enemy"])
    _bind(p)
    a = FakeActuator(p)
    map_view.return_to_top(p, a, sleep=lambda s: None, attempts=2)
    assert (1170, 90) in a.taps  # default mode still nudges


def test_return_to_top_strict_mode_still_cancels_substate_via_return_button():
    # strict mode loses nothing where it matters: the 返回 button is drawn in
    # every selection substate, so the overlay is still escaped by it alone.
    p = FakePerception(["unit_move", "hub"])
    _bind(p)
    a = FakeActuator(p)
    reached = map_view.return_to_top(
        p, a, sleep=lambda s: None, allow_neutral_nudge=False
    )
    assert reached is True
    assert a.taps == [(1805, 975)]  # only the 返回 button center, no map cell
