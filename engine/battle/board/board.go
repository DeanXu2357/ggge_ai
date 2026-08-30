package board

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

var _ battle.Board = (*Board)(nil)

type Board struct {
	state battle.BattleState
}
