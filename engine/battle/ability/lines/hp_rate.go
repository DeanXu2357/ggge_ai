package lines

import "github.com/DeanXu2357/ggge_ai/engine/battle/ability"

// The lines of the panel that hold on the HP of the holder, read at each
// strike from the HP of that moment: "(HP conditions) Increased ATK LV 3",
// "(HP conditions) Increased DEF LV 2" and their kin.

// hpRateAtMost holds when the HP of the unit, in percent of its maximum, is
// at or below the threshold. The comparison is in integers: HP × 100 against
// the threshold × MaxHP.
func hpRateAtMost(u ability.Unit, threshold int) bool {
	return u.HP*100 <= threshold*u.MaxHP
}

func hpRateAtLeast(u ability.Unit, threshold int) bool {
	return u.HP*100 >= threshold*u.MaxHP
}

// MechAttackPercentAtHPRateAtMost: "When HP is 25% or below, increase own
// ATK by 25%."
type MechAttackPercentAtHPRateAtMost struct {
	Threshold int
	Percent   float64
}

func (l MechAttackPercentAtHPRateAtMost) Clone() ability.Line { return l }
func (l MechAttackPercentAtHPRateAtMost) OnAttack(a *ability.AttackContext) {
	if hpRateAtMost(a.Attacker, l.Threshold) {
		a.MechAttackPercent += l.Percent
	}
}

// MechDefensePercentAtHPRateAtMost: "When HP is 50% or below, increase own
// DEF by 10%."
type MechDefensePercentAtHPRateAtMost struct {
	Threshold int
	Percent   float64
}

func (l MechDefensePercentAtHPRateAtMost) Clone() ability.Line { return l }
func (l MechDefensePercentAtHPRateAtMost) OnDefend(d *ability.DefendContext) {
	if hpRateAtMost(d.Defender, l.Threshold) {
		d.MechDefensePercent += l.Percent
	}
}

// MechDefensePercentAtHPRateAtLeast: "When HP is full, increase DEF by 20%"
// is the threshold 100.
type MechDefensePercentAtHPRateAtLeast struct {
	Threshold int
	Percent   float64
}

func (l MechDefensePercentAtHPRateAtLeast) Clone() ability.Line { return l }
func (l MechDefensePercentAtHPRateAtLeast) OnDefend(d *ability.DefendContext) {
	if hpRateAtLeast(d.Defender, l.Threshold) {
		d.MechDefensePercent += l.Percent
	}
}
