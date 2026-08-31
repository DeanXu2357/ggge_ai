package board

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

var _ battle.Board = (*Board)(nil)

type Board struct {
	state battle.BattleState
}

func NewBoard(bounds battle.Bounds, terrain battle.Terrain,
	terrainCells []battle.TerrainCell, enemies []battle.Unit) (*Board, error) {
	state := battle.BattleState{
		Units:        enemies,
		Phase:        battle.FactionAlly,
		Turn:         1,
		Bounds:       &bounds,
		Terrain:      terrain,
		TerrainCells: terrainCells,
	}
	for index := range state.Units {
		unit := &state.Units[index]
		assemble(unit)
		if unit.Faction != battle.FactionEnemy {
			return nil, fmt.Errorf("the unit %q of 'enemies' carries the faction %q",
				unit.ID, unit.Faction)
		}
		if !unit.Footprint().Within(bounds) {
			return nil, fmt.Errorf("the unit %q stands outside the board", unit.ID)
		}
	}
	for _, entry := range state.TerrainCells {
		if !(battle.Footprint{Anchor: entry.Cell, Size: battle.Cell{1, 1}}).Within(bounds) {
			return nil, fmt.Errorf("the terrain cell %v stands outside the board", entry.Cell)
		}
	}
	out := &Board{state: state.Clone()}
	if err := validate(&out.state); err != nil {
		return nil, err
	}
	return out, nil
}

func Restore(state *battle.BattleState) (*Board, error) {
	if state == nil {
		return nil, fmt.Errorf("the payload carries no state")
	}
	out := &Board{state: state.Clone()}
	if err := validate(&out.state); err != nil {
		return nil, err
	}
	return out, nil
}

// A maximum that the payload leaves at zero comes from the pairing. An
// explicit value stands: an ability of the pilot or of the mech can lift the
// maximum above the base data (issue #77).
func assemble(unit *battle.Unit) {
	if unit.MaxHP == 0 {
		unit.MaxHP = unit.Mech.HP
	}
	if unit.ENMax == 0 {
		unit.ENMax = unit.Mech.EN
	}
	if unit.SPMax == 0 {
		unit.SPMax = unit.Pilot.SP
	}
}
