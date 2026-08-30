package board

import (
	"fmt"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/engagement"
	"github.com/DeanXu2357/ggge_ai/engine/battle/turn"
)

type resolution struct {
	Trace     engagement.Trace
	Rotations []turn.Rotation
}

func (b *Board) Act(action *battle.Decision, dice battle.Dice) ([]any, error) {
	decision, err := decodeDecision(action)
	if err != nil {
		return nil, err
	}
	resolution, err := b.act(decision, dice)
	if err != nil {
		return nil, err
	}
	return encodeResolution(resolution), nil
}

func (b *Board) act(decision engagement.Decision, dice battle.Dice) (resolution, error) {
	plan, err := engagement.Prepare(&b.state, decision)
	if err != nil {
		return resolution{}, err
	}
	if !dice.Covers(plan.Draws()) {
		return resolution{}, fmt.Errorf(
			"%w: the 'outcomes' list holds fewer labels than the %d draws the action can make",
			battle.ErrOutsideContract, plan.Draws())
	}
	trace := engagement.Commit(&b.state, plan, dice)
	return resolution{Trace: trace, Rotations: turn.Advance(&b.state)}, nil
}
