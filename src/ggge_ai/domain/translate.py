from __future__ import annotations

from ..goap.state import WorldState
from ..perception.base import GameState


def to_world_state(game_state: GameState) -> WorldState:
    # dark story/animation frames classify as arbitrary screens with low
    # confidence; planning on them would send actions to the wrong screen
    screen = game_state.screen if game_state.screen_confidence >= 0.9 else "unknown"
    facts: dict = {"screen": screen}
    if game_state.battle is not None:
        facts["my_turn"] = game_state.battle.my_turn
        facts["all_enemies_defeated"] = game_state.battle.enemies_alive == 0
    return WorldState(facts)
