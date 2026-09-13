package system

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

func Gone(board state.Battle) []battle.Faction {
	var out []battle.Faction
	for _, faction := range []battle.Faction{battle.FactionAlly, battle.FactionEnemy} {
		if !holds(board, faction) {
			out = append(out, faction)
		}
	}
	return out
}

func holds(board state.Battle, faction battle.Faction) bool {
	for _, unit := range board.Units() {
		if unit.Faction == faction && unit.Alive() {
			return true
		}
	}
	return false
}
