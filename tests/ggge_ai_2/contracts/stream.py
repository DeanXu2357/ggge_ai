from collections.abc import Sequence

import pytest

from ggge_ai_2.stream.contract import Frame, NoFrame, Stream
from tests.ggge_ai_2.fakes.stream import flicker, frames, steady


class StreamContract:
    """Subclass per implementation and build a stream that replays the given frames."""

    def make(self, timeline: Sequence[Frame]) -> Stream:
        raise NotImplementedError

    def test_settled_returns_only_frames_after_the_cutoff(self):
        stream = self.make(frames(*steady(1, 0.1, 1.0)))

        assert stream.settled(after=0.5, deadline=5.0).frame.captured_at > 0.5

    def test_still_window_ends_at_the_returned_frame(self):
        obs = self.make(frames(*steady(1, 0.1, 1.0))).settled(after=0.3, deadline=5.0)

        assert obs.still is not None
        assert 0.3 < obs.still.since <= obs.still.until == obs.frame.captured_at
        assert obs.still.frame_seq == obs.frame.seq

    def test_changing_screen_has_no_still_window_at_the_deadline(self):
        obs = self.make(frames(*flicker((1, 2), 0.1, 2.0))).settled(after=0.0, deadline=1.0)

        assert obs.still is None
        assert obs.frame.captured_at <= 1.0

    def test_no_frame_after_the_cutoff_raises(self):
        stream = self.make(frames(*steady(1, 0.1, 1.0)))

        with pytest.raises(NoFrame):
            stream.settled(after=10.0, deadline=11.0)

    def test_latest_does_not_go_back_in_time(self):
        stream = self.make(frames(*steady(1, 0.1, 1.0)))
        times = [stream.latest().captured_at for _ in range(5)]

        assert times == sorted(times)
