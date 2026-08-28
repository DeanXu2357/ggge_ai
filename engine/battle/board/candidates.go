package board

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func (b *Board) Capabilities(unitID string) (protocol.ActionsResponse, error) {
	capabilities, err := b.capabilities(unitID)
	if err != nil {
		return protocol.ActionsResponse{}, err
	}
	return encodeCapabilities(capabilities), nil
}

func (b *Board) capabilities(unitID string) (Capabilities, error) {
	unit, err := b.livingUnit(unitID)
	if err != nil {
		return Capabilities{}, err
	}
	if unit.Faction != b.phase {
		return Capabilities{}, fmt.Errorf("%w: %q is of the side %q, and the phase is %q",
			battle.ErrOffPhase, unitID, unit.Faction, b.phase)
	}
	cells, err := b.reachableCells(unitID)
	if err != nil {
		return Capabilities{}, err
	}
	return Capabilities{Unit: unit, MoveCells: cells}, nil
}
