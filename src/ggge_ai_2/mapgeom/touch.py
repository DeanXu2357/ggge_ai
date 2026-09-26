from dataclasses import dataclass

from ggge_ai_2.actuator.contract import TouchPoint
from ggge_ai_2.display import Display
from ggge_ai_2.stream.contract import FramePoint


@dataclass(frozen=True)
class FrameToTouch:
    display: Display

    def __call__(self, point: FramePoint) -> TouchPoint:
        touch, frame = self.display.touch, self.display.frame
        return TouchPoint(
            round(point.x * touch.width / frame.width),
            round(point.y * touch.height / frame.height),
        )
