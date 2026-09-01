package board

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/engagement"
	"github.com/DeanXu2357/ggge_ai/engine/battle/geometry"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
	"github.com/DeanXu2357/ggge_ai/engine/battle/turn"
)

func (b *Board) Actions(unitID int) (battle.ActionsResponse, error) {
	unit, err := engagement.Activatable(&b.state, unitID)
	if err != nil {
		return battle.ActionsResponse{}, err
	}
	return actionsOf(unitID, unit,
		geometry.SortedCells(geometry.ReachableAnchors(&b.state, unitID))), nil
}

func actionsOf(unitID int, unit *state.Unit, moveCells []battle.Cell) battle.ActionsResponse {
	return battle.ActionsResponse{
		Unit:       unitStatusOf(unitID, unit),
		MoveCells:  moveCells,
		Weapons:    weaponEntriesOf(unit),
		MapWeapons: mapWeaponEntriesOf(unit),
		Skills:     skillEntriesOf(unit.Value.Skills),
	}
}

func (b *Board) ReachableCells(unitID int) ([]battle.Cell, error) {
	if _, err := engagement.LivingUnit(&b.state, unitID); err != nil {
		return nil, err
	}
	return geometry.SortedCells(geometry.ReachableAnchors(&b.state, unitID)), nil
}

func (b *Board) ResponseAttacks(action *battle.Decision, defenderID int) (battle.ResponseAttacksResponse, error) {
	options, err := engagement.Menu(&b.state, *action, defenderID)
	if err != nil {
		return battle.ResponseAttacksResponse{}, err
	}
	return responseAttacksOf(options), nil
}

func (b *Board) State() battle.BattleState {
	return b.state.ToContract()
}

func (b *Board) Summary() battle.BoardSummary {
	out := battle.BoardSummary{
		Turn: b.state.Turn, Phase: b.state.Phase,
		PendingIDs: []int{}, Gone: []battle.Faction{},
	}
	out.PendingIDs = append(out.PendingIDs, turn.Pending(&b.state, b.state.Phase)...)
	out.Gone = append(out.Gone, turn.Gone(&b.state)...)
	return out
}
