package board

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle/engagement"
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
	unit, err := engagement.LivingUnit(&b.state, unitID)
	if err != nil {
		return capabilities{}, err
	}
	if err := engagement.OnPhase(&b.state, unit); err != nil {
		return capabilities{}, err
	}
	cells, err := b.reachableCells(unitID)
	if err != nil {
		return capabilities{}, err
	}
	return capabilities{Unit: unit, MoveCells: cells}, nil
}
