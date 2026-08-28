package differential_test

import (
	"encoding/json"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/board"
	"github.com/DeanXu2357/ggge_ai/engine/differential"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func init() {
	addOps(resolveOps)
}

type forcedDice struct {
	AttackerSupport bool `json:"attacker_support"`
	DefenderSupport bool `json:"defender_support"`
	Strike          bool `json:"strike"`
	Counter         bool `json:"counter"`
}

type applyInput struct {
	Decision protocol.Decision `json:"decision"`
	Dice     forcedDice        `json:"dice"`
}

type applyAnswer struct {
	Units []protocol.Unit `json:"units"`
}

var resolveOps = map[string]differential.Op{
	"apply": func(setup *differential.Setup, input json.RawMessage) (any, error) {
		var in applyInput
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
		if _, err := state.Apply(decision, battle.Forced(in.Dice)); err != nil {
			return nil, err
		}
		return applyAnswer{Units: livingUnits(state)}, nil
	},
}

func livingUnits(state *board.Board) []protocol.Unit {
	roster := state.Roster()
	out := make([]battle.Unit, 0, len(roster))
	for _, unit := range roster {
		if unit.Alive() {
			out = append(out, unit)
		}
	}
	return board.EncodeUnits(out)
}

// Six rules of the engine part from the Python oracle on purpose. The three
// resolution boards and the op above keep the six out of the comparison:
//
//  1. The engine reads the orthogonal distance between two footprints. Python
//     reads the king step. Each unit of these boards covers one cell, and each
//     unit stands in one row with the other units.
//  2. The engine reads the field 'usable_after_move' of the weapon and of the
//     skill. Python infers the permission from the kind of the action. No
//     decision here carries a move, and each actor holds a move range of 0.
//  3. An illegal move is an error in the engine. Python drops it in silence.
//     No decision here carries a move.
//  4. A destroyed unit stays on the board with no hit points left. Python
//     removes it at the end of 'step'. The op filters its answer on the life of
//     the unit, and the expectation of Python holds the same units.
//  5. The client names the support units of each side (issue #63). Python fires
//     every eligible supporter on every attack, and it picks the support defender
//     itself. Each decision here names the units that Python picked, so the two
//     runtimes fire the same units.
//  6. The support attack of the attacking side and the support attack of the
//     defending side are two chance nodes of the engine. Python settles both
//     with the one field 'support_hit'. The dice object of each check gives the
//     two nodes the same outcome.
//  7. A defender that carries a shield defends with it (issue #63, the ruling of
//     2026-08-25). Python holds a shield stance beside the defend stance, and it
//     reads the defend multiplier for a shielded unit that defends. The defend
//     case of the shielded unit left the comparison; the shield case stayed and
//     names the stance 'defend'.
//
// The Python 'step' rotates the phase when the acting side holds no unit that
// waits. Each acting side of these boards keeps one more unit that has not
// acted, so no case compares a state after a rotation.
func TestTheResolutionBoardsRunTheApplyOp(t *testing.T) {
	ran := 0
	for _, one := range load(t) {
		for _, op := range differential.Run(one, ops).Ran {
			if op == "apply" {
				ran++
			}
		}
	}

	if ran == 0 {
		t.Error("no case holds a check of \"apply\"")
	}
}

func TestAnApplyInputOutsideTheContractStopsTheOp(t *testing.T) {
	op := ops["apply"]

	_, err := op(nil, json.RawMessage(`{"decision":{"unit_id":"a1"},"morale":7}`))

	if err == nil {
		t.Fatal("a field that the op does not hold must stop the check")
	}
}
