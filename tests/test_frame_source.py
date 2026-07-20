"""FrameSource contract: fixture replay yields the manifest series in
order with hints derived from the pan labels."""

from pathlib import Path

from ggge_ai.battle.frame_source import FixtureFrameSource, MapFrame, hint_from_label

SERIES = Path(__file__).parent / "fixtures" / "vision" / "map_scan" / "ex2if_20260719"


def test_fixture_series_loads_in_order():
    frames = FixtureFrameSource(SERIES).collect()
    assert len(frames) == 9
    assert all(isinstance(f, MapFrame) and f.image is not None for f in frames)
    assert [f.hint for f in frames] == [
        None, "up", "up", "up", "up", "right", "down", "down", "down",
    ]
    assert all(f.measured_shift is None for f in frames)


def test_hint_from_label():
    assert hint_from_label("pt2_pan_up") == "up"
    assert hint_from_label("pt6_pan_right") == "right"
    assert hint_from_label("pt1_first_anchor") is None
