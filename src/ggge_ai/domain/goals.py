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
