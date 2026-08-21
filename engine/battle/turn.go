package battle

import "math"

// A Rotation is one phase boundary that the turn cycle crossed: the turn and
// the side that acts after it, with the stage events that fired at it.
type Rotation struct {
	Turn  int
	Phase Faction
	Fired []string
}

// A Resolution is the whole answer of one activation: the strikes of the
// engagement, the stage events that the outcome fired, and the phase
// boundaries that the turn cycle crossed after it.
type Resolution struct {
	Trace     Trace
	Fired     []string
	Rotations []Rotation
}

// Act runs one decision and then the turn cycle. An error leaves the board as
// it was.
func (b *Board) Act(decision Decision, dice Dice) (Resolution, error) {
	trace, err := b.Apply(decision, dice)
	if err != nil {
		return Resolution{}, err
	}
	return Resolution{
		Trace:     trace,
		Fired:     b.eventsAfterAct(),
		Rotations: b.AdvanceUntilPending(),
	}, nil
}

// PendingUnits gives the living units of the faction that have not acted, in
// board order.
func (b *Board) PendingUnits(faction Faction) []*Unit {
	var out []*Unit
	for index := range b.Units {
		unit := &b.Units[index]
		if unit.Faction == faction && unit.Alive() && !unit.Acted {
			out = append(out, unit)
		}
	}
	return out
}

// AdvanceUntilPending rotates the phase while the side to act holds no unit
// that waits. The guard bounds a board on which no side can act: it permits one
// rotation more than the phase order, so the answer names the side that would
// act next and the run still stops.
func (b *Board) AdvanceUntilPending() []Rotation {
	var out []Rotation
	for guard := 0; guard <= len(PhaseOrder) && len(b.PendingUnits(b.Phase)) == 0; guard++ {
		out = append(out, b.rotate())
	}
	return out
}

// rotate hands the board to the next side of the phase order. A rotation that
// comes back to the ally side opens a new turn, and the stage events of that
// turn fire before the side takes its phase.
func (b *Board) rotate() Rotation {
	next := PhaseOrder[(phaseSlot(b.Phase)+1)%len(PhaseOrder)]
	var fired []string
	if next == FactionAlly {
		b.Turn++
		fired = b.eventsOnNewTurn()
	}
	b.Phase = next
	b.expireDebuffs()
	b.BeginPhase(next)
	return Rotation{Turn: b.Turn, Phase: b.Phase, Fired: fired}
}

// BeginPhase refreshes the side that starts its phase: every unit takes its
// activation back, refills its chance steps and its support charges, and
// regenerates a fraction of its energy (docs/reference/combat-formulas.md).
func (b *Board) BeginPhase(faction Faction) {
	for index := range b.Units {
		unit := &b.Units[index]
		if unit.Faction != faction || !unit.Alive() {
			continue
		}
		unit.Acted = false
		unit.ChanceSteps = unit.ChanceStepsMax
		unit.SupportDefendCharges = unit.SupportDefendChargesMax
		unit.SupportAttackCharges = unit.SupportAttackChargesMax
		unit.EN = min(unit.ENMax, unit.EN+b.energyRegen(unit))
	}
}

// The oracle rounds the regenerated energy with the Python 'round', which takes
// a half to the even integer.
func (b *Board) energyRegen(unit *Unit) int {
	return int(math.RoundToEven(float64(unit.ENMax) * b.Rules.ENRegenFraction))
}

// A debuff lives for one full round of the phase order
// (docs/reference/combat-formulas.md).
func (b *Board) expireDebuffs() {
	now := b.PhaseIndex()
	for index := range b.Units {
		unit := &b.Units[index]
		kept := unit.Debuffs[:0]
		for _, debuff := range unit.Debuffs {
			if now-debuff.AppliedPhase < len(PhaseOrder) {
				kept = append(kept, debuff)
			}
		}
		unit.Debuffs = kept
	}
}
