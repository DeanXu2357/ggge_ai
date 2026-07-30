"""感知與裝置接縫：批 2d 接上實機通道後，這裡釘住接縫本身的契約。"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from ggge_ai.contracts import Ending
from ggge_ai.runtime import screens
from ggge_ai.runtime.device import LiveDevice, LiveExecutor, UnsupportedAction
from ggge_ai.runtime.perceive import LivePerceiver, Observation, classify, decode, read
from tests.fixtures.frames import load


def png_bytes(frame: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".png", frame)
    assert ok
    return buffer.tobytes()


class FakeAdb:
    def __init__(self, frame: bytes) -> None:
        self.frame = frame
        self.commands: list[str] = []

    def screencap(self) -> bytes:
        return self.frame

    def shell(self, command: str) -> str:
        self.commands.append(command)
        return ""


def test_an_observation_defaults_to_no_reading_and_no_terminal():
    observation = Observation[str](screen="battle_map")

    assert observation.state is None
    assert observation.terminal is None
    assert observation.evidence == {}


def test_a_terminal_observation_carries_the_ending_the_screen_shows():
    observation = Observation[str](screen="battle_result", terminal=Ending.VICTORY)

    assert observation.terminal is Ending.VICTORY


def test_the_perceiver_hands_back_the_native_png_bytes_it_captured():
    """原生幀位元組直通：screencap 給什麼位元組，Observation.frame 就是那些
    位元組——中途不重新編碼，流水帳才復現得出當下看到的東西。"""
    raw = png_bytes(load("stage_panels/battle_map_turn1_r2"))
    perceiver = LivePerceiver(device=LiveDevice(adb=FakeAdb(raw)))

    observation = perceiver.look()

    assert observation.frame == raw
    assert observation.screen == screens.BATTLE_MAP
    assert observation.evidence["auto"] == screens.AUTO_OFF
    assert observation.evidence["frame_sig"]
    assert observation.state is None


def test_the_perceiver_flags_the_result_screen_as_terminal():
    raw = png_bytes(load("stage_panels/battle_map_turn1_r2"))
    perceiver = LivePerceiver(
        device=LiveDevice(adb=FakeAdb(raw)), terminals={screens.BATTLE_MAP: Ending.VICTORY}
    )

    assert perceiver.look().terminal is Ending.VICTORY


def test_the_symbolic_reader_is_injected_not_assumed():
    """runtime 不認識 StageState：符號讀取由 stage 層注入。"""
    raw = png_bytes(load("stage_panels/battle_map_turn1_r2"))
    seen: list[str] = []

    def reader(frame, screen):
        seen.append(screen)
        return "symbolic"

    perceiver = LivePerceiver(device=LiveDevice(adb=FakeAdb(raw)), reader=reader)

    assert perceiver.look().state == "symbolic"
    assert seen == [screens.BATTLE_MAP]


def test_decode_refuses_bytes_that_are_not_an_image():
    with pytest.raises(ValueError):
        decode(b"not a png")


def test_decode_passes_an_array_straight_through():
    frame = np.zeros((4, 4, 3), np.uint8)

    assert decode(frame) is frame
    assert decode(None) is None


def test_the_module_level_helpers_read_a_frame_without_a_device():
    frame = load("stage_panels/stage_info_conditions")

    assert classify(frame) == screens.STAGE_INFO
    assert read(frame)["auto"] == screens.AUTO_ON
    assert read(None) == {}


def test_an_action_with_no_gesture_plan_is_a_loud_error():
    executor = LiveExecutor(device=object())

    with pytest.raises(UnsupportedAction):
        executor.perform(object(), Observation(screen="battle_map"))
