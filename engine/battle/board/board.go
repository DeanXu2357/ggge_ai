package board

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

var _ battle.Board = (*Board)(nil)

type Board struct {
	state state.Battle
}

func New() *Board {
	return &Board{}
}
