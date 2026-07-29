"""感知與裝置接縫：批 1a 只立介面，真實作留到接實機那批。"""

from __future__ import annotations

import pytest

from ggge_ai.contracts import Ending
from ggge_ai.runtime.device import LiveDevice, LiveExecutor
from ggge_ai.runtime.perceive import LivePerceiver, Observation, classify, read


def test_the_live_implementations_are_still_unbuilt():
    with pytest.raises(NotImplementedError):
        LivePerceiver().look()
    with pytest.raises(NotImplementedError):
        LiveDevice().screenshot()
    with pytest.raises(NotImplementedError):
        LiveDevice().tap(0, 0)
    with pytest.raises(NotImplementedError):
        LiveDevice().swipe(0, 0, 1, 1, 0.1)
    with pytest.raises(NotImplementedError):
        LiveExecutor().perform(object(), Observation(screen="x"))
    with pytest.raises(NotImplementedError):
        classify(object())
    with pytest.raises(NotImplementedError):
        read(object())


def test_an_observation_defaults_to_no_reading_and_no_terminal():
    observation = Observation[str](screen="battle_map")

    assert observation.state is None
    assert observation.terminal is None
    assert observation.evidence == {}


def test_a_terminal_observation_carries_the_ending_the_screen_shows():
    observation = Observation[str](screen="battle_result", terminal=Ending.VICTORY)

    assert observation.terminal is Ending.VICTORY
