package board

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

var _ battle.Board = (*Board)(nil)

type Board struct {
	state battle.BattleState
}

func New() *Board {
	return &Board{}
}

func (b *Board) Load(bounds battle.Bounds, terrain battle.Terrain,
	terrainCells []battle.TerrainCell, units []battle.Unit,
	phase battle.Faction, turn int) error {
	candidate := battle.BattleState{
		Units:        units,
		Phase:        phase,
		Turn:         turn,
		Bounds:       &bounds,
		Terrain:      terrain,
		TerrainCells: terrainCells,
	}
	for index := range candidate.Units {
		assemble(&candidate.Units[index])
	}
	if err := validate(&candidate); err != nil {
		return err
	}
	for index := range candidate.Units {
		unit := &candidate.Units[index]
		if !unit.Footprint().Within(bounds) {
			return fmt.Errorf("the unit %q stands outside the board", unit.ID)
		}
	}
	for _, entry := range candidate.TerrainCells {
		if !(battle.Footprint{Anchor: entry.Cell, Size: battle.Cell{1, 1}}).Within(bounds) {
			return fmt.Errorf("the terrain cell %v stands outside the board", entry.Cell)
		}
	}
	b.state = candidate.Clone()
	return nil
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
