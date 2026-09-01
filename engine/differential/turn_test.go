package differential_test

import (
	"encoding/json"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/differential"
)

func init() {
	addOps(turnOps)
}

type actInput struct {
	Decision battle.Decision `json:"decision"`
	Outcomes []string        `json:"outcomes"`
}

type actAnswer struct {
	Turn       int            `json:"turn"`
	Phase      battle.Faction `json:"phase"`
	PendingIDs []int          `json:"pending_ids"`
	Units      []battle.Unit  `json:"units"`
}

// The two turn-cycle cases are hand-derived; no oracle wrote them.
var turnOps = map[string]differential.Op{
	"act": func(setup *differential.Setup, input json.RawMessage) (any, error) {
		var in actInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		state, err := restoreBoard(&setup.State)
		if err != nil {
			return nil, err
		}
		outcomes, err := battle.DecodeOutcomes(in.Outcomes)
		if err != nil {
			return nil, err
		}
		roll := battle.NewManualRoll(outcomes)
		if _, err := state.Act(&in.Decision, roll); err != nil {
			return nil, err
		}
		summary := state.Summary()
		return actAnswer{Turn: summary.Turn, Phase: summary.Phase, PendingIDs: summary.PendingIDs, Units: livingUnits(state)}, nil
	},
}
