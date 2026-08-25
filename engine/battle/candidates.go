package battle

import "fmt"

type Capabilities struct {
	Unit      *Unit
	MoveCells []Cell
}

func (b *Board) Capabilities(unitID string) (Capabilities, error) {
	unit, err := b.livingUnit(unitID)
	if err != nil {
		return Capabilities{}, err
	}
	if unit.Faction != b.Phase {
		return Capabilities{}, fmt.Errorf("%w: %q is of the side %q, and the phase is %q",
			ErrOffPhase, unitID, unit.Faction, b.Phase)
	}
	cells, err := b.ReachableCells(unitID)
	if err != nil {
		return Capabilities{}, err
	}
	return Capabilities{Unit: unit, MoveCells: cells}, nil
}
