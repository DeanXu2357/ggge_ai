package board

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/engagement"
	"github.com/DeanXu2357/ggge_ai/engine/battle/turn"
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

func (b *Board) ReachableCells(unitID string) ([]protocol.Cell, error) {
	unit, err := engagement.LivingUnit(&b.state, unitID)
	if err != nil {
		return nil, err
	}
	return encodeCells(b.reachableCells(unit)), nil
}

func (b *Board) ResponseAttacks(action *protocol.Decision, defenderID string) (protocol.ResponseAttacksResponse, error) {
	decision, err := DecodeDecision(action)
	if err != nil {
		return protocol.ResponseAttacksResponse{}, err
	}
	options, err := engagement.Menu(&b.state, decision, defenderID)
	if err != nil {
		return protocol.ResponseAttacksResponse{}, err
	}
	return encodeOptions(options), nil
}

func (b *Board) Clone() battle.Board {
	return &Board{state: b.state.Clone()}
}

func (b *Board) State() protocol.BattleState {
	bounds := protocol.Bounds{encodeCell(b.state.Bounds.Low), encodeCell(b.state.Bounds.High)}
	return protocol.BattleState{
		Units:         encodeUnits(b.state.Units),
		Phase:         wireFactions[b.state.Phase],
		Turn:          b.state.Turn,
		Bounds:        &bounds,
		PendingEvents: []string{},
		FiredEvents:   []string{},
		Terrain:       terrainName(b.state.DefaultTerrain),
		TerrainCells:  encodeTerrainCells(b.state.TerrainCells),
	}
}

func (b *Board) Summary() protocol.BoardSummary {
	out := protocol.BoardSummary{
		Turn: b.state.Turn, Phase: wireFactions[b.state.Phase],
		Pending: []string{}, Gone: []protocol.Faction{},
	}
	for _, unit := range turn.Pending(&b.state, b.state.Phase) {
		out.Pending = append(out.Pending, unit.ID)
	}
	for _, faction := range turn.Gone(&b.state) {
		out.Gone = append(out.Gone, wireFactions[faction])
	}
	return out
}
