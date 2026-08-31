package board

import "github.com/DeanXu2357/ggge_ai/engine/battle"

var _ battle.BoardFactory = Factory{}

type Factory struct{}

func (Factory) NewBoard(bounds battle.Bounds, terrain battle.Terrain,
	terrainCells []battle.TerrainCell, enemies []battle.Unit) (battle.Board, error) {
	out, err := NewBoard(bounds, terrain, terrainCells, enemies)
	if err != nil {
		return nil, err
	}
	return out, nil
}

func (Factory) Restore(state *battle.BattleState) (battle.Board, error) {
	out, err := Restore(state)
	if err != nil {
		return nil, err
	}
	return out, nil
}
