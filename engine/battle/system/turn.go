package system

import (
	"slices"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

const enRegenPercent = 10

// A board with no living unit keeps its phase: every side would stay empty,
// and the rotation would never end.
func rotate(board state.Battle) []battle.PhaseEvent {
	if !anyAlive(board) {
		return nil
	}
	var out []battle.PhaseEvent
	for len(Pending(board, board.Values.Phase)) == 0 {
		out = append(out, nextPhase(board))
	}
	return out
}

func nextPhase(board state.Battle) battle.PhaseEvent {
	values := board.Values
	slot := (values.PhaseIndex() - values.Turn*len(battle.PhaseOrder) + 1) % len(battle.PhaseOrder)
	if slot == 0 {
		values.Turn++
	}
	values.Phase = battle.PhaseOrder[slot]
	return battle.PhaseEvent{Kind: battle.EventPhase, Turn: values.Turn, Phase: values.Phase,
		Effects: beginPhase(board)}
}

func beginPhase(board state.Battle) []battle.Effect {
	now := board.Values.PhaseIndex()
	var led ledger
	for id, unit := range board.Units() {
		if !unit.Alive() {
			continue
		}
		if kept := expired(unit.Value.Debuffs, now); len(kept) != len(unit.Value.Debuffs) {
			led.unit(id).Debuffs = changeDebuffs(&unit.Value.Debuffs, kept)
		}
		if unit.Faction != board.Values.Phase {
			continue
		}
		if unit.Value.Acted {
			led.unit(id).Acted = change(&unit.Value.Acted, false)
		}
		if regen := min(unit.ENMax, unit.Value.EN+unit.ENMax*enRegenPercent/100); regen != unit.Value.EN {
			led.unit(id).EN = change(&unit.Value.EN, regen)
		}
	}
	return led.list()
}

func expired(debuffs []battle.Debuff, now int) []battle.Debuff {
	return slices.DeleteFunc(slices.Clone(debuffs), func(debuff battle.Debuff) bool {
		return debuff.AppliedPhase+len(battle.PhaseOrder) <= now
	})
}

func anyAlive(board state.Battle) bool {
	for _, unit := range board.Units() {
		if unit.Alive() {
			return true
		}
	}
	return false
}
