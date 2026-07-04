from __future__ import annotations

from ..core.state import WorldState
from ..perception.base import GameState


def to_world_state(game_state: GameState) -> WorldState:
    facts: dict = {"screen": game_state.screen}
    if game_state.battle is not None:
        facts["my_turn"] = game_state.battle.my_turn
        facts["all_enemies_defeated"] = game_state.battle.enemies_alive == 0
    return WorldState(facts)
