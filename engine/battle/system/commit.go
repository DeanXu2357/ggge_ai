package system

import (
	"fmt"
	"math/rand/v2"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/geometry"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

func Commit(board state.Battle, action battle.Action, draw *rand.Rand) (state.Values, []battle.Event, error) {
	actor, err := Activatable(board, action.ActorID)
	if err != nil {
		return state.Values{}, nil, err
	}
	if action.MapAttack != nil {
		return state.Values{}, nil, fmt.Errorf("%w: the engine fires no map weapon, because the area of a map weapon is not in the contract",
			battle.ErrIllegalAction)
	}
	if (action.Attack == nil) != (action.ResponseAttack == nil) {
		return state.Values{}, nil, fmt.Errorf("%w: an attack and its response attack travel together",
			battle.ErrIllegalAction)
	}
	if action.Attack == nil {
		if _, err := destination(board, action.ActorID, action.MoveTo, true); err != nil {
			return state.Values{}, nil, err
		}
		return board.Values.Clone(), nil, nil
	}
	anchor, err := checkAttack(board, action, actor)
	if err != nil {
		return state.Values{}, nil, err
	}
	firing := geometry.FootprintAt(actor, anchor)
	target := unitOf(board, action.Attack.TargetID)
	dodging := action.ResponseAttack.Stance == battle.StanceDodge
	if err := checkSide(board, action.ActorID, firing, target, target.Footprint(), dodging,
		action.Attack.SupportAttackers, action.Attack.SupportDefenderID); err != nil {
		return state.Values{}, nil, err
	}
	if err := checkResponse(board, action, actor, firing); err != nil {
		return state.Values{}, nil, err
	}
	if err := checkSide(board, action.Attack.TargetID, target.Footprint(), actor, firing, false,
		action.ResponseAttack.SupportAttackers, action.ResponseAttack.SupportDefenderID); err != nil {
		return state.Values{}, nil, err
	}
	return board.Values.Clone(), nil, nil
}
