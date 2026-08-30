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

func (b *Board) capabilities(unitID string) (capabilities, error) {
	unit, err := b.livingUnit(unitID)
	if err != nil {
		return capabilities{}, err
	}
	if unit.Faction != b.state.Phase {
		return capabilities{}, fmt.Errorf("%w: %q is of the side %q, and the phase is %q",
			battle.ErrOffPhase, unitID, unit.Faction, b.state.Phase)
	}
	cells, err := b.reachableCells(unitID)
	if err != nil {
		return capabilities{}, err
	}
	return capabilities{Unit: unit, MoveCells: cells}, nil
}
