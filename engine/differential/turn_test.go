package differential_test

import (
	"encoding/json"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/differential"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func init() {
	addOps(turnOps)
}

type actInput struct {
	Decision protocol.Decision `json:"decision"`
	Dice     forcedDice        `json:"dice"`
}

// actAnswer holds what one activation leaves behind: the living units, the side
// that acts, the turn, and the two event lists.
type actAnswer struct {
	Units         []protocol.Unit  `json:"units"`
	Phase         protocol.Faction `json:"phase"`
	Turn          int              `json:"turn"`
	PendingEvents []string         `json:"pending_events"`
	FiredEvents   []string         `json:"fired_events"`
}

var turnOps = map[string]differential.Op{
	"act": func(setup *differential.Setup, input json.RawMessage) (any, error) {
		var in actInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		board, err := battle.DecodeState(&setup.State)
		if err != nil {
			return nil, err
		}
		if board.Rules, err = battle.DecodeRules(&setup.Rules); err != nil {
			return nil, err
		}
		if board.Events, err = battle.DecodeEvents(setup.Events); err != nil {
			return nil, err
		}
		decision, err := battle.DecodeDecision(in.Decision)
		if err != nil {
			return nil, err
		}
		if _, err := board.Act(decision, battle.Forced(in.Dice)); err != nil {
			return nil, err
		}
		state := battle.EncodeState(board)
		return actAnswer{
			Units:         livingUnits(board),
			Phase:         state.Phase,
			Turn:          state.Turn,
			PendingEvents: state.PendingEvents,
			FiredEvents:   state.FiredEvents,
		}, nil
	},
}

// The turn-cycle boards keep every diverging rule out of the comparison, on top
// of the six that 'resolve_test.go' names:
//
//  7. Python removes a destroyed unit from the board and the engine keeps it
//     with no hit points left. The answer of the op filters on life.
//  8. A spawn skips an identity that the board holds, and the engine holds a
//     destroyed unit. No spawn of these boards carries the identity of a unit
//     that the board already held.
//
// Each unit of these boards covers one cell, stands in one row and holds a move
// range of 0, and no decision names a reaction.
func TestTheTurnCycleBoardsRunTheActOp(t *testing.T) {
	ran := 0
	for _, one := range load(t) {
		for _, op := range differential.Run(one, ops).Ran {
			if op == "act" {
				ran++
			}
		}
	}

	if ran == 0 {
		t.Error("no case holds a check of \"act\"")
	}
}
