package system

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

// LivingUnit and onPhase are the two gates that every command reads, so the
// shell asks them here and no package writes the refusal twice.
func LivingUnit(board state.Battle, unitID int) (state.Unit, error) {
	u, err := livingUnit(board, unitID)
	return u.toStateUnit(), err
}

func livingUnit(board state.Battle, unitID int) (unit, error) {
	u, err := findUnit(board, unitID)
	if err != nil {
		return unit{}, err
	}
	if !u.Alive() {
		return unit{}, fmt.Errorf("%w: %d", battle.ErrDestroyed, unitID)
	}
	return u, nil
}
