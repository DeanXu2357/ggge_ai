package differential_test

import (
	"encoding/json"
	"errors"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/board"
	"github.com/DeanXu2357/ggge_ai/engine/differential"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func init() {
	addOps(turnOps)
}

type actInput struct {
	Decision protocol.Decision `json:"decision"`
	Outcomes []string          `json:"outcomes"`
}

type actAnswer struct {
	Turn    int              `json:"turn"`
	Phase   protocol.Faction `json:"phase"`
	Pending []string         `json:"pending"`
	Units   []protocol.Unit  `json:"units"`
}

// The two turn-cycle cases are hand-derived; no oracle wrote them.
var turnOps = map[string]differential.Op{
	"act": func(setup *differential.Setup, input json.RawMessage) (any, error) {
		var in actInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		state, err := board.DecodeState(&setup.State)
		if err != nil {
			return nil, err
		}
		decision, err := board.DecodeDecision(&in.Decision)
		if err != nil {
			return nil, err
		}
		outcomes, err := board.DecodeOutcomes(in.Outcomes)
		if err != nil {
			return nil, err
		}
		roll := battle.NewManualRoll(outcomes)
		if _, err := state.Act(decision, roll); err != nil {
			return nil, err
		}
		if roll.Short() {
			return nil, errors.New("the 'outcomes' list is short")
		}
		summary := board.EncodeSummary(state)
		return actAnswer{Turn: summary.Turn, Phase: summary.Phase, Pending: summary.Pending, Units: livingUnits(state)}, nil
	},
}
