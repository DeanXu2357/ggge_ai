package system

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

func Pending(board state.Battle, faction battle.Faction) []int {
	var out []int
	for index, unit := range board.Units() {
		if unit.Faction == faction && unit.Alive() && !unit.Value.Acted {
			out = append(out, index)
		}
	}
	return out
}
