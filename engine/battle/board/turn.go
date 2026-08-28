package board

import "github.com/DeanXu2357/ggge_ai/engine/battle"

func (b *Board) Act(decision battle.Decision, dice battle.Dice) (battle.Resolution, error) {
	trace, err := b.Apply(decision, dice)
	if err != nil {
		return battle.Resolution{}, err
	}
	return battle.Resolution{Trace: trace, Rotations: b.Advance()}, nil
}

func (b *Board) pending(faction battle.Faction) []*battle.Unit {
	var out []*battle.Unit
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
func (b *Board) Advance() []battle.Rotation {
	if !b.anyAlive() {
		return nil
	}
	var out []battle.Rotation
	for len(b.pending(b.phase)) == 0 {
		out = append(out, b.nextPhase())
	}
	return out
}

func (b *Board) nextPhase() battle.Rotation {
	slot := (b.PhaseIndex() - b.turn*len(PhaseOrder) + 1) % len(PhaseOrder)
	if slot == 0 {
		b.turn++
	}
	b.phase = PhaseOrder[slot]
	b.beginPhase()
	return battle.Rotation{Turn: b.turn, Phase: b.phase}
}

func (b *Board) beginPhase() {
	now := b.PhaseIndex()
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

func expired(debuffs []battle.Debuff, now int) []battle.Debuff {
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

func (b *Board) gone() []battle.Faction {
	var out []battle.Faction
	for _, faction := range []battle.Faction{battle.FactionAlly, battle.FactionEnemy} {
		if len(b.ByFaction(faction)) == 0 {
			out = append(out, faction)
		}
	}
	return out
}
