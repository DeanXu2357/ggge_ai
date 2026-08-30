package turn

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

const enRegenPercent = 10

type Rotation struct {
	Turn  int
	Phase battle.Faction
}

// A board with no living unit keeps its phase: every side would stay empty,
// and the rotation would never end.
func Advance(board *battle.BattleState) []Rotation {
	if !anyAlive(board) {
		return nil
	}
	var out []Rotation
	for len(Pending(board, board.Phase)) == 0 {
		out = append(out, nextPhase(board))
	}
	return out
}

func Pending(board *battle.BattleState, faction battle.Faction) []*battle.Unit {
	var out []*battle.Unit
	for index := range board.Units {
		unit := &board.Units[index]
		if unit.Faction == faction && unit.Alive() && !unit.Acted {
			out = append(out, unit)
		}
	}
	return out
}

func Gone(board *battle.BattleState) []battle.Faction {
	var out []battle.Faction
	for _, faction := range []battle.Faction{battle.FactionAlly, battle.FactionEnemy} {
		if !holds(board, faction) {
			out = append(out, faction)
		}
	}
	return out
}

func nextPhase(board *battle.BattleState) Rotation {
	slot := (board.PhaseIndex() - board.Turn*len(battle.PhaseOrder) + 1) % len(battle.PhaseOrder)
	if slot == 0 {
		board.Turn++
	}
	board.Phase = battle.PhaseOrder[slot]
	beginPhase(board)
	return Rotation{Turn: board.Turn, Phase: board.Phase}
}

func beginPhase(board *battle.BattleState) {
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

func expired(debuffs []battle.Debuff, now int) []battle.Debuff {
	kept := debuffs[:0]
	for _, debuff := range debuffs {
		if debuff.AppliedPhase+len(battle.PhaseOrder) > now {
			kept = append(kept, debuff)
		}
	}
	return kept
}

func anyAlive(board *battle.BattleState) bool {
	for index := range board.Units {
		if board.Units[index].Alive() {
			return true
		}
	}
	return false
}

func holds(board *battle.BattleState, faction battle.Faction) bool {
	for index := range board.Units {
		unit := &board.Units[index]
		if unit.Faction == faction && unit.Alive() {
			return true
		}
	}
	return false
}
