import numpy as np

from ggge_ai.perception.base import Bbox, UiElement
from ggge_ai.vision.base import ScreenCandidate
from ggge_ai.vision.pipeline import RecognizerPipeline, Stage

IMG = np.zeros((10, 10, 3), dtype=np.uint8)


class FakeRecognizer:
    def __init__(self, name, screens=(), elements=(), texts=()):
        self.name = name
        self.screens = list(screens)
        self.elements = list(elements)
        self.texts = list(texts)
        self.calls = 0

    def classify_screen(self, img):
        self.calls += 1
        return self.screens

    def detect_elements(self, img, element_ids):
        self.calls += 1
        return [e for e in self.elements if e.id in element_ids]

    def read_text(self, img, region=None):
        self.calls += 1
        return self.texts


def element(eid, confidence):
    return UiElement(id=eid, bbox=Bbox(0, 0, 5, 5), confidence=confidence)


def test_screen_short_circuits_on_confident_match():
    fast = FakeRecognizer("fast", screens=[ScreenCandidate("main_menu", 0.95)])
    slow = FakeRecognizer("slow", screens=[ScreenCandidate("main_menu", 0.99)])
    pipeline = RecognizerPipeline(
        screen_stages=[Stage(fast, accept_above=0.9), Stage(slow, accept_above=0.5)]
    )
    result = pipeline.classify_screen(IMG)
    assert result.confidence == 0.95
    assert slow.calls == 0


def test_screen_falls_back_when_low_confidence():
    fast = FakeRecognizer("fast", screens=[ScreenCandidate("main_menu", 0.4)])
    slow = FakeRecognizer("slow", screens=[ScreenCandidate("stage_select", 0.8)])
    pipeline = RecognizerPipeline(
        screen_stages=[Stage(fast, accept_above=0.9), Stage(slow, accept_above=0.5)]
    )
    result = pipeline.classify_screen(IMG)
    assert result.screen == "stage_select"
    assert slow.calls == 1


def test_screen_keeps_best_when_all_below_threshold():
    a = FakeRecognizer("a", screens=[ScreenCandidate("x", 0.4)])
    b = FakeRecognizer("b", screens=[ScreenCandidate("y", 0.3)])
    pipeline = RecognizerPipeline(
        screen_stages=[Stage(a, accept_above=0.9), Stage(b, accept_above=0.9)]
    )
    result = pipeline.classify_screen(IMG)
    assert result.screen == "x"


def test_elements_second_stage_only_gets_missing_ids():
    first = FakeRecognizer("first", elements=[element("btn_a", 0.95)])
    second = FakeRecognizer("second", elements=[element("btn_a", 0.99), element("btn_b", 0.7)])
    pipeline = RecognizerPipeline(
        element_stages=[Stage(first, accept_above=0.8), Stage(second, accept_above=0.5)]
    )
    found = pipeline.detect_elements(IMG, ["btn_a", "btn_b"])
    by_id = {e.id: e for e in found}
    assert by_id["btn_a"].confidence == 0.95
    assert by_id["btn_b"].confidence == 0.7


def test_elements_all_found_skips_later_stages():
    first = FakeRecognizer("first", elements=[element("btn_a", 0.95)])
    second = FakeRecognizer("second")
    pipeline = RecognizerPipeline(
        element_stages=[Stage(first, accept_above=0.8), Stage(second)]
    )
    pipeline.detect_elements(IMG, ["btn_a"])
    assert second.calls == 0
