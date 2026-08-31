package board

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/engagement"
	"github.com/DeanXu2357/ggge_ai/engine/battle/geometry"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
	"github.com/DeanXu2357/ggge_ai/engine/battle/turn"
)

func (b *Board) Actions(unitID string) (battle.ActionsResponse, error) {
	unit, err := engagement.Activatable(&b.state, unitID)
	if err != nil {
		return battle.ActionsResponse{}, err
	}
	return actionsOf(unit, geometry.SortedCells(geometry.ReachableAnchors(&b.state, unit))), nil
}

func actionsOf(unit *state.Unit, moveCells []battle.Cell) battle.ActionsResponse {
	return battle.ActionsResponse{
		Unit:       encodeUnitStatus(unit),
		MoveCells:  moveCells,
		Weapons:    encodeWeapons(unit),
		MapWeapons: encodeMapWeapons(unit),
		Skills:     encodeSkills(unit.Value.Skills),
	}
}

func (b *Board) ReachableCells(unitID string) ([]battle.Cell, error) {
	unit, err := engagement.LivingUnit(&b.state, unitID)
	if err != nil {
		return nil, err
	}
	return geometry.SortedCells(geometry.ReachableAnchors(&b.state, unit)), nil
}

func (b *Board) ResponseAttacks(action *battle.Decision, defenderID string) (battle.ResponseAttacksResponse, error) {
	options, err := engagement.Menu(&b.state, *action, defenderID)
	if err != nil {
		return battle.ResponseAttacksResponse{}, err
	}
	return encodeOptions(options), nil
}

func (b *Board) State() battle.BattleState {
	return b.state.ToContract()
}

func (b *Board) Summary() battle.BoardSummary {
	out := battle.BoardSummary{
		Turn: b.state.Turn, Phase: b.state.Phase,
		Pending: []string{}, Gone: []battle.Faction{},
	}
	for _, unit := range turn.Pending(&b.state, b.state.Phase) {
		out.Pending = append(out.Pending, unit.ID)
	}
	out.Gone = append(out.Gone, turn.Gone(&b.state)...)
	return out
}
