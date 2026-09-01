package board

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

var _ battle.Board = (*Board)(nil)

type Board struct {
	content state.Content
	values  state.Values
}

func New() *Board {
	return &Board{}
}

func (b *Board) compose() state.Battle {
	return state.Compose(&b.content, b.values)
}
