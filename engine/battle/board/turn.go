package board

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

const enRegenPercent = 10

func (b *Board) Act(action *protocol.Decision, dice battle.Dice) ([]any, error) {
	decision, err := DecodeDecision(action)
	if err != nil {
		return nil, err
	}
	resolution, err := b.act(decision, dice)
	if err != nil {
		return nil, err
	}
	return encodeResolution(resolution), nil
}

func (b *Board) act(decision decision, dice battle.Dice) (resolution, error) {
	trace, err := b.Apply(decision, dice)
	if err != nil {
		return resolution{}, err
	}
	return resolution{Trace: trace, Rotations: b.Advance()}, nil
}

func (b *Board) pending(faction faction) []*Unit {
	var out []*Unit
	for index := range b.units {
		unit := &b.units[index]
		if unit.Faction == faction && unit.alive() && !unit.Acted {
			out = append(out, unit)
		}
	}
	return out
}

// A board with no living unit keeps its phase: every side would stay empty,
// and the rotation would never end.
func (b *Board) Advance() []rotation {
	if !b.anyAlive() {
		return nil
	}
	var out []rotation
	for len(b.pending(b.phase)) == 0 {
		out = append(out, b.nextPhase())
	}
	return out
}

func (b *Board) nextPhase() rotation {
	slot := (b.phaseIndex() - b.turn*len(phaseOrder) + 1) % len(phaseOrder)
	if slot == 0 {
		b.turn++
	}
	b.phase = phaseOrder[slot]
	b.beginPhase()
	return rotation{Turn: b.turn, Phase: b.phase}
}

func (b *Board) beginPhase() {
	now := b.phaseIndex()
	for index := range b.units {
		unit := &b.units[index]
		if !unit.alive() {
			continue
		}
		unit.Debuffs = expired(unit.Debuffs, now)
		if unit.Faction != b.phase {
			continue
		}
		unit.Acted = false
		unit.EN = min(unit.ENMax, unit.EN+unit.ENMax*enRegenPercent/100)
	}
}

func expired(debuffs []debuff, now int) []debuff {
	kept := debuffs[:0]
	for _, debuff := range debuffs {
		if debuff.AppliedPhase+len(phaseOrder) > now {
			kept = append(kept, debuff)
		}
	}
	return kept
}

func (b *Board) anyAlive() bool {
	for index := range b.units {
		if b.units[index].alive() {
			return true
		}
	}
	return false
}

func (b *Board) gone() []faction {
	var out []faction
	for _, faction := range []faction{factionAlly, factionEnemy} {
		if len(b.byFaction(faction)) == 0 {
			out = append(out, faction)
		}
	}
	return out
}
