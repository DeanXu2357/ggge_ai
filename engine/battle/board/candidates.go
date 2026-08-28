package board

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

func (b *Board) Capabilities(unitID string) (battle.Capabilities, error) {
	unit, err := b.livingUnit(unitID)
	if err != nil {
		return battle.Capabilities{}, err
	}
	if unit.Faction != b.phase {
		return battle.Capabilities{}, fmt.Errorf("%w: %q is of the side %q, and the phase is %q",
			battle.ErrOffPhase, unitID, unit.Faction, b.phase)
	}
	cells, err := b.ReachableCells(unitID)
	if err != nil {
		return battle.Capabilities{}, err
	}
	return battle.Capabilities{Unit: unit, MoveCells: cells}, nil
}
