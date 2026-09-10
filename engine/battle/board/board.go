package board

import (
	"math/rand/v2"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

var _ battle.Board = (*Board)(nil)

type Board struct {
	content state.Content
	values  state.Values
	source  *rand.PCG
}

func New(seed int64) *Board {
	return &Board{source: rand.NewPCG(uint64(seed), 0)}
}

func (b *Board) view() state.Battle {
	return state.Battle{Content: &b.content, Values: &b.values}
}
