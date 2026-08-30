package board

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/engagement"
	"github.com/DeanXu2357/ggge_ai/engine/battle/turn"
)

func (b *Board) Actions(unitID string) (battle.ActionsResponse, error) {
	unit, err := engagement.Activatable(&b.state, unitID)
	if err != nil {
		return battle.ActionsResponse{}, err
	}
	return encodeActions(unit, b.reachableCells(unit)), nil
}

func (b *Board) ReachableCells(unitID string) ([]battle.Cell, error) {
	unit, err := engagement.LivingUnit(&b.state, unitID)
	if err != nil {
		return nil, err
	}
	return encodeCells(b.reachableCells(unit)), nil
}

func (b *Board) ResponseAttacks(action *battle.Decision, defenderID string) (battle.ResponseAttacksResponse, error) {
	decision, err := decodeDecision(action)
	if err != nil {
		return battle.ResponseAttacksResponse{}, err
	}
	options, err := engagement.Menu(&b.state, decision, defenderID)
	if err != nil {
		return battle.ResponseAttacksResponse{}, err
	}
	return encodeOptions(options), nil
}

func (b *Board) Clone() battle.Board {
	return &Board{state: b.state.Clone()}
}

func (b *Board) State() battle.BattleState {
	bounds := battle.Bounds{encodeCell(b.state.Bounds.Low), encodeCell(b.state.Bounds.High)}
	return battle.BattleState{
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

func (b *Board) Summary() battle.BoardSummary {
	out := battle.BoardSummary{
		Turn: b.state.Turn, Phase: wireFactions[b.state.Phase],
		Pending: []string{}, Gone: []battle.Faction{},
	}
	for _, unit := range turn.Pending(&b.state, b.state.Phase) {
		out.Pending = append(out.Pending, unit.ID)
	}
	for _, faction := range turn.Gone(&b.state) {
		out.Gone = append(out.Gone, wireFactions[faction])
	}
	return out
}
