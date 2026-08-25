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

type reactionsInput struct {
	DefenderID   string        `json:"defender_id"`
	AttackerID   string        `json:"attacker_id"`
	AttackerCell protocol.Cell `json:"attacker_cell"`
	WeaponID     string        `json:"weapon_id"`
}

var candidateOps = map[string]differential.Op{
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

// Three rules of the engine diverge from the Python oracle on purpose. The
// reaction board and the op above keep the three out of the comparison:
//
//  1. The engine reads the orthogonal distance between two footprints. It also
//     reads the anchors that the whole footprint reaches. Python reads the king
//     step. Python gives every unit one cell. Each unit of these boards covers
//     one cell. Each unit stands in one row with the other units. A support
//     unit keeps its move range, because that range is its support reach.
//  2. The engine writes no 'none' stance. The Python writer drops that stance
//     before it encodes the list.
//  3. The engine reads the field 'usable_after_move' of the weapon. Python
//     infers the permission from the kind of the action. A unit that cannot
//     move fires from its own anchor in the two runtimes.
//
// Both sides sort the list before the comparison, so the order of the
// enumeration is no part of this test.
func TestTheCandidateBoardsRunTheReactionOp(t *testing.T) {
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

	if ran["reactions"] == 0 {
		t.Error("no case holds a check of \"reactions\"")
	}
}

func TestACandidateInputOutsideTheContractStopsTheOp(t *testing.T) {
	op := ops["reactions"]

	if _, err := op(nil, json.RawMessage(`{"defender_id":"e1","morale":7}`)); err == nil {
		t.Fatal("a field that the op does not hold must stop the check")
	}
}
