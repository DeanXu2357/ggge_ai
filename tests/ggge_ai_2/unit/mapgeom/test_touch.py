from ggge_ai_2.actuator.contract import TouchPoint
from ggge_ai_2.display import Display, Size
from ggge_ai_2.mapgeom.touch import FrameToTouch
from ggge_ai_2.stream.contract import FramePoint

DEVICE = Size(2340, 1080)


def test_full_size_frame_maps_one_to_one():
    to_touch = FrameToTouch(Display(touch=DEVICE, frame=DEVICE))

    assert to_touch(FramePoint(1204.4, 618.6)) == TouchPoint(1204, 619)


def test_scaled_frame_maps_back_to_device_pixels():
    to_touch = FrameToTouch(Display(touch=DEVICE, frame=Size(1170, 540)))

    assert to_touch(FramePoint(602.0, 309.0)) == TouchPoint(1204, 618)
