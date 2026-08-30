package board

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/geometry"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

var _ battle.Board = (*Board)(nil)

type Board struct {
	state state.Board
}

func newBoard(bounds state.Bounds, units []state.Unit) (*Board, error) {
	if bounds.High[0] < bounds.Low[0] || bounds.High[1] < bounds.Low[1] {
		return nil, fmt.Errorf("the bounds %v run backward", bounds)
	}
	seen := make(map[string]bool, len(units))
	for index := range units {
		id := units[index].ID
		if seen[id] {
			return nil, fmt.Errorf("the board holds two units with the id %q", id)
		}
		seen[id] = true
	}
	return &Board{state: state.Board{Bounds: bounds, Units: units}}, nil
}

func (b *Board) terrainAt(cell state.Cell) state.Terrain {
	if kind, declared := b.state.TerrainCells[cell]; declared {
		return kind
	}
	return b.state.DefaultTerrain
}

func (b *Board) terrainOf(unit *state.Unit) state.Terrain {
	if unit == nil {
		return b.state.DefaultTerrain
	}
	return b.terrainAt(unit.Footprint.Anchor)
}

func (b *Board) unit(id string) *state.Unit {
	return b.state.Unit(id)
}

func (b *Board) reachableCells(unit *state.Unit) []state.Cell {
	return geometry.SortedCells(geometry.ReachableAnchors(&b.state, unit))
}
