package deploy

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

// A maximum that the payload leaves at zero comes from the pairing. An
// explicit value stands: an ability of the pilot or of the mech can lift the
// maximum above the base data (issue #77).
func Assemble(unit *battle.Unit) {
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

func Opening(bounds battle.Bounds, terrain battle.Terrain, terrainCells []battle.TerrainCell,
	enemies []battle.Unit) (battle.BattleState, error) {
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
		Assemble(unit)
		if unit.Faction != battle.FactionEnemy {
			return battle.BattleState{}, fmt.Errorf("the unit %q of 'enemies' carries the faction %q",
				unit.ID, unit.Faction)
		}
		if !unit.Footprint().Within(bounds) {
			return battle.BattleState{}, fmt.Errorf("the unit %q stands outside the board", unit.ID)
		}
	}
	for _, entry := range state.TerrainCells {
		if !(battle.Footprint{Anchor: entry.Cell, Size: battle.Cell{1, 1}}).Within(bounds) {
			return battle.BattleState{}, fmt.Errorf("the terrain cell %v stands outside the board", entry.Cell)
		}
	}
	return state, nil
}
