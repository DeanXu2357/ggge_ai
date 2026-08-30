package turn

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

const enRegenPercent = 10

type Rotation struct {
	Turn  int
	Phase state.Faction
}

// A board with no living unit keeps its phase: every side would stay empty,
// and the rotation would never end.
func Advance(board *state.Board) []Rotation {
	if !anyAlive(board) {
		return nil
	}
	var out []Rotation
	for len(Pending(board, board.Phase)) == 0 {
		out = append(out, nextPhase(board))
	}
	return out
}

func Pending(board *state.Board, faction state.Faction) []*state.Unit {
	var out []*state.Unit
	for index := range board.Units {
		unit := &board.Units[index]
		if unit.Faction == faction && unit.Alive() && !unit.Acted {
			out = append(out, unit)
		}
	}
	return out
}

func Gone(board *state.Board) []state.Faction {
	var out []state.Faction
	for _, faction := range []state.Faction{state.FactionAlly, state.FactionEnemy} {
		if !holds(board, faction) {
			out = append(out, faction)
		}
	}
	return out
}

func nextPhase(board *state.Board) Rotation {
	slot := (board.PhaseIndex() - board.Turn*len(state.PhaseOrder) + 1) % len(state.PhaseOrder)
	if slot == 0 {
		board.Turn++
	}
	board.Phase = state.PhaseOrder[slot]
	beginPhase(board)
	return Rotation{Turn: board.Turn, Phase: board.Phase}
}

func beginPhase(board *state.Board) {
	now := board.PhaseIndex()
	for index := range board.Units {
		unit := &board.Units[index]
		if !unit.Alive() {
			continue
		}
		unit.Debuffs = expired(unit.Debuffs, now)
		if unit.Faction != board.Phase {
			continue
		}
		unit.Acted = false
		unit.EN = min(unit.ENMax, unit.EN+unit.ENMax*enRegenPercent/100)
	}
}

func expired(debuffs []state.Debuff, now int) []state.Debuff {
	kept := debuffs[:0]
	for _, debuff := range debuffs {
		if debuff.AppliedPhase+len(state.PhaseOrder) > now {
			kept = append(kept, debuff)
		}
	}
	return kept
}

func anyAlive(board *state.Board) bool {
	for index := range board.Units {
		if board.Units[index].Alive() {
			return true
		}
	}
	return false
}

func holds(board *state.Board, faction state.Faction) bool {
	for index := range board.Units {
		unit := &board.Units[index]
		if unit.Faction == faction && unit.Alive() {
			return true
		}
	}
	return false
}
