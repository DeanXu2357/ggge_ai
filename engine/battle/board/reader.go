package board

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/engagement"
	"github.com/DeanXu2357/ggge_ai/engine/battle/geometry"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
	"github.com/DeanXu2357/ggge_ai/engine/battle/turn"
)

func (b *Board) Actions(unitID int) (battle.ActionsResponse, error) {
	working := b.compose()
	unit, err := engagement.Activatable(&working, unitID)
	if err != nil {
		return battle.ActionsResponse{}, err
	}
	return actionsOf(unitID, unit,
		geometry.SortedCells(geometry.ReachableAnchors(&working, unitID))), nil
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
	working := b.compose()
	if _, err := engagement.LivingUnit(&working, unitID); err != nil {
		return nil, err
	}
	return geometry.SortedCells(geometry.ReachableAnchors(&working, unitID)), nil
}

func (b *Board) ResponseAttacks(action *battle.Decision, defenderID int) (battle.ResponseAttacksResponse, error) {
	options, err := engagement.Menu(b.content, b.values, *action, defenderID)
	if err != nil {
		return battle.ResponseAttacksResponse{}, err
	}
	return responseAttacksOf(options), nil
}

func (b *Board) State() battle.BattleState {
	working := b.compose()
	return working.ToContract()
}

func (b *Board) Summary() battle.BoardSummary {
	working := b.compose()
	out := battle.BoardSummary{
		Turn: working.Turn, Phase: working.Phase,
		PendingIDs: []int{}, Gone: []battle.Faction{},
	}
	out.PendingIDs = append(out.PendingIDs, turn.Pending(&working, working.Phase)...)
	out.Gone = append(out.Gone, turn.Gone(&working)...)
	return out
}
