package board

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle/engagement"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func (b *Board) Actions(unitID string) (protocol.ActionsResponse, error) {
	unit, err := engagement.LivingUnit(&b.state, unitID)
	if err != nil {
		return protocol.ActionsResponse{}, err
	}
	if err := engagement.OnPhase(&b.state, unit); err != nil {
		return protocol.ActionsResponse{}, err
	}
	return encodeActions(unit, b.reachableCells(unit)), nil
}
