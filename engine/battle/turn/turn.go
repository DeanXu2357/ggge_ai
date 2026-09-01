package turn

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
func Advance(board *state.Battle) []Rotation {
	if !anyAlive(board) {
		return nil
	}
	var out []Rotation
	for len(Pending(board, board.Phase)) == 0 {
		out = append(out, nextPhase(board))
	}
	return out
}

func Pending(board *state.Battle, faction battle.Faction) []*state.Unit {
	var out []*state.Unit
	for index := range board.Units {
		unit := &board.Units[index]
		if unit.Faction == faction && unit.Alive() && !unit.Value.Acted {
			out = append(out, unit)
		}
	}
	return out
}

func Gone(board *state.Battle) []battle.Faction {
	var out []battle.Faction
	for _, faction := range []battle.Faction{battle.FactionAlly, battle.FactionEnemy} {
		if !holds(board, faction) {
			out = append(out, faction)
		}
	}
	return out
}

func nextPhase(board *state.Battle) Rotation {
	slot := (board.PhaseIndex() - board.Turn*len(battle.PhaseOrder) + 1) % len(battle.PhaseOrder)
	if slot == 0 {
		board.Turn++
	}
	board.Phase = battle.PhaseOrder[slot]
	beginPhase(board)
	return Rotation{Turn: board.Turn, Phase: board.Phase}
}

func beginPhase(board *state.Battle) {
	now := board.PhaseIndex()
	for index := range board.Units {
		unit := &board.Units[index]
		if !unit.Alive() {
			continue
		}
		unit.Value.Debuffs = expired(unit.Value.Debuffs, now)
		if unit.Faction != board.Phase {
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

func anyAlive(board *state.Battle) bool {
	for index := range board.Units {
		if board.Units[index].Alive() {
			return true
		}
	}
	return false
}

func holds(board *state.Battle, faction battle.Faction) bool {
	for index := range board.Units {
		unit := &board.Units[index]
		if unit.Faction == faction && unit.Alive() {
			return true
		}
	}
	return false
}
