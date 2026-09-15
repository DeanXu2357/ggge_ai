package system

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

func Activatable(board state.Battle, unitID int) (state.Unit, error) {
	u, err := activatable(board, unitID)
	return u.toStateUnit(), err
}

func activatable(board state.Battle, unitID int) (unit, error) {
	u, err := livingUnit(board, unitID)
	if err != nil {
		return unit{}, err
	}
	if !onPhase(board, u) {
		return unit{}, fmt.Errorf("%w: the side %q does not hold the phase %q",
			battle.ErrOffPhase, u.Faction, board.Values.Phase)
	}
	if u.Value.Acted {
		return unit{}, fmt.Errorf("%w: %d", battle.ErrActed, unitID)
	}
	return u, nil
}

func onPhase(board state.Battle, u unit) bool {
	return u.Faction == board.Values.Phase
}
