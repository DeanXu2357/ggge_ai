package board

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

var _ battle.Board = (*Board)(nil)

type Board struct {
	state battle.BattleState
}

func NewBoard(state *battle.BattleState) (*Board, error) {
	if state == nil {
		return nil, fmt.Errorf("the payload carries no state")
	}
	out := &Board{state: state.Clone()}
	if err := validate(&out.state); err != nil {
		return nil, err
	}
	return out, nil
}
