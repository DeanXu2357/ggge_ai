package system

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

const enRegenPercent = 10

type Rotation struct {
	Turn  int
	Phase battle.Faction
}

// A board with no living unit keeps its phase: every side would stay empty,
// and the rotation would never end.
func Advance(board state.Battle) (state.Values, []Rotation) {
	working := board.Values.Clone()
	scratch := state.Battle{Content: board.Content, Values: &working}
	if !anyAlive(scratch) {
		return working, nil
	}
	var out []Rotation
	for len(Pending(scratch, working.Phase)) == 0 {
		out = append(out, nextPhase(scratch))
	}
	return working, out
}

func nextPhase(board state.Battle) Rotation {
	values := board.Values
	slot := (values.PhaseIndex() - values.Turn*len(battle.PhaseOrder) + 1) % len(battle.PhaseOrder)
	if slot == 0 {
		values.Turn++
	}
	values.Phase = battle.PhaseOrder[slot]
	beginPhase(board)
	return Rotation{Turn: values.Turn, Phase: values.Phase}
}

func beginPhase(board state.Battle) {
	now := board.Values.PhaseIndex()
	for _, unit := range board.Units() {
		if !unit.Alive() {
			continue
		}
		unit.Value.Debuffs = expired(unit.Value.Debuffs, now)
		if unit.Faction != board.Values.Phase {
			continue
		}
		unit.Value.Acted = false
		unit.Value.EN = min(unit.ENMax, unit.Value.EN+unit.ENMax*enRegenPercent/100)
	}
}

func expired(debuffs []battle.Debuff, now int) []battle.Debuff {
	kept := debuffs[:0]
	for _, debuff := range debuffs {
		if debuff.AppliedPhase+len(battle.PhaseOrder) > now {
			kept = append(kept, debuff)
		}
	}
	return kept
}

func anyAlive(board state.Battle) bool {
	for _, unit := range board.Units() {
		if unit.Alive() {
			return true
		}
	}
	return false
}
