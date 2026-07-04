from __future__ import annotations

from ...core.action import Action, ExecutionContext
from ...perception.base import ScreenId


class TapNavigate(Action):
    """Tap a named element on from_screen, transitioning to to_screen."""

    def __init__(
        self,
        element_id: str,
        from_screen: ScreenId,
        to_screen: ScreenId,
        cost: float = 1.0,
        extra_preconditions: dict | None = None,
        extra_effects: dict | None = None,
    ) -> None:
        self.element_id = element_id
        self.name = f"tap:{element_id}@{from_screen}"
        self.cost = cost
        self.preconditions = {"screen": from_screen, **(extra_preconditions or {})}
        self.effects = {"screen": to_screen, **(extra_effects or {})}

    def execute(self, ctx: ExecutionContext) -> bool:
        if ctx.game_state is None:
            return False
        element = ctx.game_state.find_element(self.element_id)
        if element is None:
            return False
        ctx.actuator.tap(*element.bbox.center)
        return True
