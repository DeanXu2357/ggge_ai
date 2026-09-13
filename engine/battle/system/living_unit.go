package system

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

// LivingUnit and onPhase are the two gates that every command reads, so the
// shell asks them here and no package writes the refusal twice.
func LivingUnit(board state.Battle, unitID int) (state.Unit, error) {
	unit, err := board.UnitAt(unitID)
	if err != nil {
		return state.Unit{}, err
	}
	if !unit.Alive() {
		return state.Unit{}, fmt.Errorf("%w: %d", battle.ErrDestroyed, unitID)
	}
	return unit, nil
}
