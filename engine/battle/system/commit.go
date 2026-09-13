package system

import (
	"math/rand/v2"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

func Commit(board state.Battle, action battle.Action, draw *rand.Rand) (state.Values, []battle.Event, error) {
	if err := check(board, action); err != nil {
		return state.Values{}, nil, err
	}
	working := board.Values.Clone()
	return working, nil, nil
}
