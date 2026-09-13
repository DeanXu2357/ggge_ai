package system

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

func Activatable(board state.Battle, unitID int) (state.Unit, error) {
	unit, err := LivingUnit(board, unitID)
	if err != nil {
		return state.Unit{}, err
	}
	if !onPhase(board, unit) {
		return state.Unit{}, fmt.Errorf("%w: the side %q does not hold the phase %q",
			battle.ErrOffPhase, unit.Faction, board.Values.Phase)
	}
	if unit.Value.Acted {
		return state.Unit{}, fmt.Errorf("%w: %d", battle.ErrActed, unitID)
	}
	return unit, nil
}

func onPhase(board state.Battle, unit state.Unit) bool {
	return unit.Faction == board.Values.Phase
}
