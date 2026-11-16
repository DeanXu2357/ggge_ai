from __future__ import annotations

import json

import pytest

from ggge_ai_2.actuator.contract import Key, Swipe, Tap
from ggge_ai_2.agent.contract import MapReadingRecord, MapTap
from ggge_ai_2.agent.trace_json import decode_record, encode_gesture, encode_record
from ggge_ai_2.interpreter.contract import Phase
from ggge_ai_2.mapparser.opencv_parser import OpenCvMapParser
from ggge_ai_2.stream.contract import Frame, StillWindow
from tests.ggge_ai_2.dataset import cases, load_image
from tests.ggge_ai_2.unit.mapparser.scope import scope_of

# An enemy panel with name masks, a tap mark with terrain, and a map with neither.
CASES = ("map20261112-1", "map20261112-5", "rec20261014-672")


@pytest.mark.parametrize("case_id", CASES)
def test_a_record_reads_back_from_its_json_form(case_id: str):
    case = next(case for case in cases() if case.id == case_id)
    reading = OpenCvMapParser().parse(Frame(load_image(case), 0.0, 0), scope_of(case))
    assert reading is not None
    record = MapReadingRecord(StillWindow(1.5, 2.5, 9), reading, Phase.PLAYER, 3)

    data = json.loads(json.dumps(encode_record(record)))

    assert encode_record(decode_record(data)) == data


def test_each_gesture_has_a_json_form():
    gestures = (None, Tap((1, 2)), Swipe((1, 2), (3, 4), 0.5), MapTap((5, 6)), Key("BACK"))

    assert [encode_gesture(gesture) for gesture in gestures] == [
        None,
        {"kind": "tap", "point": [1, 2]},
        {"kind": "swipe", "start": [1, 2], "end": [3, 4], "duration": 0.5},
        {"kind": "map_tap", "cell": [5, 6]},
        {"kind": "key", "code": "BACK"},
    ]
