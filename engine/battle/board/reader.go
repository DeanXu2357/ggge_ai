package board

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/engagement"
	"github.com/DeanXu2357/ggge_ai/engine/battle/geometry"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
	"github.com/DeanXu2357/ggge_ai/engine/battle/turn"
)

func (b *Board) Actions(unitID int) (battle.ActionsResponse, error) {
	view := b.view()
	unit, err := engagement.Activatable(view, unitID)
	if err != nil {
		return battle.ActionsResponse{}, err
	}
	return actionsOf(unitID, unit,
		geometry.SortedCells(geometry.ReachableAnchors(view, unitID))), nil
}

func actionsOf(unitID int, unit state.Unit, moveCells []battle.Cell) battle.ActionsResponse {
	return battle.ActionsResponse{
		Unit:       unitStatusOf(unitID, unit),
		MoveCells:  moveCells,
		Weapons:    weaponEntriesOf(unit),
		MapWeapons: mapWeaponEntriesOf(unit),
		Skills:     skillEntriesOf(unit.Value.Skills),
	}
}

func (b *Board) ReachableCells(unitID int) ([]battle.Cell, error) {
	view := b.view()
	if _, err := engagement.LivingUnit(view, unitID); err != nil {
		return nil, err
	}
	return geometry.SortedCells(geometry.ReachableAnchors(view, unitID)), nil
}

func (b *Board) ResponseAttacks(action *battle.Decision, defenderID int) (battle.ResponseAttacksResponse, error) {
	options, err := engagement.Menu(b.view(), *action, defenderID)
	if err != nil {
		return battle.ResponseAttacksResponse{}, err
	}
	return responseAttacksOf(options), nil
}

func (b *Board) State() battle.BattleState {
	return b.view().ToContract()
}

func (b *Board) Summary() battle.BoardSummary {
	view := b.view()
	out := battle.BoardSummary{
		Turn: view.Values.Turn, Phase: view.Values.Phase,
		PendingIDs: []int{}, Gone: []battle.Faction{},
	}
	out.PendingIDs = append(out.PendingIDs, turn.Pending(view, view.Values.Phase)...)
	out.Gone = append(out.Gone, turn.Gone(view)...)
	return out
}
