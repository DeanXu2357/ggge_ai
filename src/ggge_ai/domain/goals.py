from __future__ import annotations

from ..core.action import Goal
from ..perception.base import ScreenId


class ReachScreen(Goal):
    def __init__(self, screen: ScreenId) -> None:
        self.name = f"reach:{screen}"
        self.conditions = {"screen": screen}


class StageCleared(Goal):
    def __init__(self, stage_id: str) -> None:
        self.name = f"clear:{stage_id}"
        self.conditions = {f"stage_cleared:{stage_id}": True}


class ClearCurrentStage(Goal):
    """Clear the stage currently selected in the stage list and return there.
    stage_cleared is latched by AutoBattle on victory; requiring the return to
    the stage list makes the loop also drain the post-battle screens."""

    name = "clear_current_stage"
    conditions = {"stage_cleared": True, "screen": "stage_list"}
