package differential_test

import (
	"encoding/json"
	"sort"
	"testing"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/differential"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

func init() {
	addOps(candidateOps)
}

type actionsInput struct {
	UnitID string `json:"unit_id"`
}

type reactionsInput struct {
	DefenderID   string        `json:"defender_id"`
	AttackerID   string        `json:"attacker_id"`
	AttackerCell protocol.Cell `json:"attacker_cell"`
	WeaponID     string        `json:"weapon_id"`
}

var candidateOps = map[string]differential.Op{
	"actions": func(setup *differential.Setup, input json.RawMessage) (any, error) {
		var in actionsInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		board, err := battle.DecodeState(&setup.State)
		if err != nil {
			return nil, err
		}
		decisions, err := board.Actions(in.UnitID)
		if err != nil {
			return nil, err
		}
		return sortedDecisions(battle.EncodeDecisions(decisions)), nil
	},
	"reactions": func(setup *differential.Setup, input json.RawMessage) (any, error) {
		var in reactionsInput
		if err := decodeInput(input, &in); err != nil {
			return nil, err
		}
		board, err := battle.DecodeState(&setup.State)
		if err != nil {
			return nil, err
		}
		options, err := board.Reactions(in.DefenderID, in.AttackerID,
			battle.DecodeCell(in.AttackerCell), in.WeaponID)
		if err != nil {
			return nil, err
		}
		return sortedReactions(battle.EncodeReactions(options)), nil
	},
}

func sortedDecisions(list []protocol.Decision) []protocol.Decision {
	sort.Slice(list, func(i, j int) bool {
		return decisionBefore(list[i], list[j])
	})
	return list
}

func decisionBefore(a, b protocol.Decision) bool {
	if a.Kind != b.Kind {
		return a.Kind < b.Kind
	}
	if name(a.TargetID) != name(b.TargetID) {
		return name(a.TargetID) < name(b.TargetID)
	}
	if name(a.Weapon) != name(b.Weapon) {
		return name(a.Weapon) < name(b.Weapon)
	}
	if order := cellOrder(a.MoveTo, b.MoveTo); order != 0 {
		return order < 0
	}
	if order := cellOrder(a.Aim, b.Aim); order != 0 {
		return order < 0
	}
	if order := amountOrder(a.Amount, b.Amount); order != 0 {
		return order < 0
	}
	return !a.Support && b.Support
}

// An amount with no value sorts before every amount, as the Python key does.
func amountOrder(a, b *float64) int {
	switch {
	case a == nil && b == nil:
		return 0
	case a == nil:
		return -1
	case b == nil:
		return 1
	case *a < *b:
		return -1
	case *b < *a:
		return 1
	}
	return 0
}

func sortedReactions(list []protocol.Reaction) []protocol.Reaction {
	sort.Slice(list, func(i, j int) bool {
		return reactionBefore(list[i], list[j])
	})
	return list
}

func reactionBefore(a, b protocol.Reaction) bool {
	if a.Stance != b.Stance {
		return a.Stance < b.Stance
	}
	if name(a.Weapon) != name(b.Weapon) {
		return name(a.Weapon) < name(b.Weapon)
	}
	if a.SupportDefend != b.SupportDefend {
		return !a.SupportDefend
	}
	return !a.SupportAttack && b.SupportAttack
}

func name(value *string) string {
	if value == nil {
		return ""
	}
	return *value
}

// A cell with no value sorts before every cell, as the Python key does.
func cellOrder(a, b *protocol.Cell) int {
	if a == nil || b == nil {
		switch {
		case a == b:
			return 0
		case a == nil:
			return -1
		default:
			return 1
		}
	}
	first, second := battle.DecodeCell(*a), battle.DecodeCell(*b)
	switch {
	case first.Before(second):
		return -1
	case second.Before(first):
		return 1
	}
	return 0
}

// Four rules of the engine diverge from the Python oracle on purpose. The two
// candidate boards and the two ops above keep the four out of the comparison:
//
//  1. The engine reads the orthogonal distance between two footprints. It also
//     reads the anchors that the whole footprint reaches. Python reads the king
//     step. Python gives every unit one cell. Each unit of these boards covers
//     one cell. Each unit stands in one row with the other units. Each unit of
//     the 'actions' inputs holds a move range of 0. A support unit keeps its
//     move range, because that range is its support reach.
//  2. The engine writes no 'none' stance. The Python writer drops that stance
//     before it encodes the list.
//  3. The engine reads the field 'usable_after_move' of the weapon. Python
//     infers the permission from the kind of the action. A unit that cannot
//     move fires from its own anchor in the two runtimes.
//  4. Python 'legal_skills' reads no area of the skill. The engine enumerates
//     only the skill whose area is the caster. Each skill of these boards holds
//     a range of 0 and a blast of 0.
//
// Both sides sort the list before the comparison, so the order of the two
// enumerations is no part of this test. The order of the engine is held in
// 'engine/battle/candidates_test.go'.
func TestTheCandidateBoardsRunBothCandidateOps(t *testing.T) {
	ran := map[string]int{}
	for _, one := range load(t) {
		result := differential.Run(one, ops)
		for _, err := range result.Errs {
			t.Errorf("%s: %v", one.Name, err)
		}
		for _, op := range result.Ran {
			ran[op]++
		}
	}

	for _, op := range []string{"actions", "reactions"} {
		if ran[op] == 0 {
			t.Errorf("no case holds a check of %q", op)
		}
	}
}

func TestACandidateInputOutsideTheContractStopsTheOp(t *testing.T) {
	op := ops["actions"]

	if _, err := op(nil, json.RawMessage(`{"unit_id":"a1","morale":7}`)); err == nil {
		t.Fatal("a field that the op does not hold must stop the check")
	}
}
