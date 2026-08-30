package board

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

func (b *Board) Clone() battle.Board {
	return &Board{state: b.state.Clone()}
}
