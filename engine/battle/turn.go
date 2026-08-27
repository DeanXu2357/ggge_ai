package battle

type Rotation struct {
	Turn  int
	Phase Faction
}

type Resolution struct {
	Trace     Trace
	Rotations []Rotation
}

func (b *Board) Act(decision Decision, dice Dice) (Resolution, error) {
	trace, err := b.Apply(decision, dice)
	if err != nil {
		return Resolution{}, err
	}
	return Resolution{Trace: trace, Rotations: b.Advance()}, nil
}

func (b *Board) Pending(faction Faction) []*Unit {
	var out []*Unit
	for index := range b.Units {
		unit := &b.Units[index]
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
	for len(b.Pending(b.Phase)) == 0 {
		out = append(out, b.nextPhase())
	}
	return out
}

func (b *Board) nextPhase() Rotation {
	slot := (b.PhaseIndex() - b.Turn*len(PhaseOrder) + 1) % len(PhaseOrder)
	if slot == 0 {
		b.Turn++
	}
	b.Phase = PhaseOrder[slot]
	b.beginPhase()
	return Rotation{Turn: b.Turn, Phase: b.Phase}
}

func (b *Board) beginPhase() {
	now := b.PhaseIndex()
	for index := range b.Units {
		unit := &b.Units[index]
		if !unit.Alive() {
			continue
		}
		unit.Debuffs = expired(unit.Debuffs, now)
		if unit.Faction != b.Phase {
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
	for index := range b.Units {
		if b.Units[index].Alive() {
			return true
		}
	}
	return false
}

func (b *Board) Gone() []Faction {
	var out []Faction
	for _, faction := range []Faction{FactionAlly, FactionEnemy} {
		if len(b.ByFaction(faction)) == 0 {
			out = append(out, faction)
		}
	}
	return out
}
