package board

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/protocol"
)

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

func (b *Board) act(decision Decision, dice battle.Dice) (Resolution, error) {
	trace, err := b.Apply(decision, dice)
	if err != nil {
		return Resolution{}, err
	}
	return Resolution{Trace: trace, Rotations: b.Advance()}, nil
}

func (b *Board) pending(faction Faction) []*Unit {
	var out []*Unit
	for index := range b.units {
		unit := &b.units[index]
		if unit.Faction == faction && unit.Alive() && !unit.Acted {
			out = append(out, unit)
		}
	}
	return out
}

// A board with no living unit keeps its phase: every side would stay empty,
// and the rotation would never end.
func (b *Board) Advance() []Rotation {
	if !b.anyAlive() {
		return nil
	}
	var out []Rotation
	for len(b.pending(b.phase)) == 0 {
		out = append(out, b.nextPhase())
	}
	return out
}

func (b *Board) nextPhase() Rotation {
	slot := (b.phaseIndex() - b.turn*len(PhaseOrder) + 1) % len(PhaseOrder)
	if slot == 0 {
		b.turn++
	}
	b.phase = PhaseOrder[slot]
	b.beginPhase()
	return Rotation{Turn: b.turn, Phase: b.phase}
}

func (b *Board) beginPhase() {
	now := b.phaseIndex()
	for index := range b.units {
		unit := &b.units[index]
		if !unit.Alive() {
			continue
		}
		unit.Debuffs = expired(unit.Debuffs, now)
		if unit.Faction != b.phase {
			continue
		}
		unit.Acted = false
		unit.EN = min(unit.ENMax, unit.EN+unit.ENMax*ENRegenPercent/100)
	}
}

func expired(debuffs []Debuff, now int) []Debuff {
	kept := debuffs[:0]
	for _, debuff := range debuffs {
		if debuff.AppliedPhase+len(PhaseOrder) > now {
			kept = append(kept, debuff)
		}
	}
	return kept
}

func (b *Board) anyAlive() bool {
	for index := range b.units {
		if b.units[index].Alive() {
			return true
		}
	}
	return false
}

func (b *Board) gone() []Faction {
	var out []Faction
	for _, faction := range []Faction{FactionAlly, FactionEnemy} {
		if len(b.byFaction(faction)) == 0 {
			out = append(out, faction)
		}
	}
	return out
}
