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


@pytest.fixture(autouse=True)
def _stub_vision(monkeypatch):
    # classify_view / collapse consult these; drive them off the fake
    monkeypatch.setattr(map_view.vision, "is_unit_detail_modal", lambda f: _CUR["modal"])
    monkeypatch.setattr(map_view.vision, "unit_cards_present", lambda f: _CUR["cards"])
    yield


_CUR = {"modal": False, "cards": False}


def _bind(perc):
    _CUR["modal"] = perc.modal
    _CUR["cards"] = perc.cards


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


def test_ensure_max_view_reaches_hub_and_collapses_list():
    p = FakePerception(["unit_move", "hub"])
    p.cards = True
    _bind(p)
    a = FakeActuator(p)

    # once the strip is collapsed, cards go away
    def tap(x, y):
        a.taps.append((x, y))
        if p.i < len(p.views) - 1:
            p.i += 1
        if (x, y) == map_view.UNIT_LIST_COLLAPSE:
            _CUR["cards"] = False

    a.tap = tap
    assert map_view.ensure_max_view(p, a, sleep=lambda s: None) is True
    assert map_view.UNIT_LIST_COLLAPSE in a.taps
