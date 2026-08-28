package board

import (
	"maps"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

func (b *Board) Clone() battle.Board {
	out := *b
	out.units = make([]unit, len(b.units))
	for index := range b.units {
		out.units[index] = b.units[index].clone()
	}
	out.terrainCells = maps.Clone(b.terrainCells)
	return &out
}
