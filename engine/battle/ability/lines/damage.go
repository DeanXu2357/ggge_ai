package lines

import (
	"slices"

	"github.com/DeanXu2357/ggge_ai/engine/battle/ability"
)

// The lines of the panel that change the damage dealt or taken. Every one
// joins the sum of ⑨.

// DamageDealtPercent: "Increase own damage dealt by 15%."
type DamageDealtPercent struct{ Percent float64 }

func (l DamageDealtPercent) Clone() ability.Line               { return l }
func (l DamageDealtPercent) OnAttack(a *ability.AttackContext) { a.DamageDealtPercent += l.Percent }

// DamageDealtPercentOnMechTag: "When piloting units with specified tags,
// increase damage dealt to enemies by 15%." A pilot line that reads the
// mech the pilot rides.
type DamageDealtPercentOnMechTag struct {
	MechTag int
	Percent float64
}

func (l DamageDealtPercentOnMechTag) Clone() ability.Line { return l }
func (l DamageDealtPercentOnMechTag) OnAttack(a *ability.AttackContext) {
	if slices.Contains(a.Attacker.Mech.Tags, l.MechTag) {
		a.DamageDealtPercent += l.Percent
	}
}

// DamageTakenPercentOnMechTag: "When piloting units with specified tags,
// reduce damage taken by 15%" is the percent -15.
type DamageTakenPercentOnMechTag struct {
	MechTag int
	Percent float64
}

func (l DamageTakenPercentOnMechTag) Clone() ability.Line { return l }
func (l DamageTakenPercentOnMechTag) OnDefend(d *ability.DefendContext) {
	if slices.Contains(d.Defender.Mech.Tags, l.MechTag) {
		d.DamageTakenPercent += l.Percent
	}
}

// DamageDealtPercentAgainstTag: "When engaging an enemy with a specified
// tag, increase damage dealt to enemies by 10%."
type DamageDealtPercentAgainstTag struct {
	EnemyTag int
	Percent  float64
}

func (l DamageDealtPercentAgainstTag) Clone() ability.Line { return l }
func (l DamageDealtPercentAgainstTag) OnAttack(a *ability.AttackContext) {
	if slices.Contains(a.Defender.Mech.Tags, l.EnemyTag) {
		a.DamageDealtPercent += l.Percent
	}
}

// DamageTakenPercentAgainstTag: "When engaging an enemy with a specified
// tag, reduce damage taken by 10%" is the percent -10.
type DamageTakenPercentAgainstTag struct {
	EnemyTag int
	Percent  float64
}

func (l DamageTakenPercentAgainstTag) Clone() ability.Line { return l }
func (l DamageTakenPercentAgainstTag) OnDefend(d *ability.DefendContext) {
	if slices.Contains(d.Attacker.Mech.Tags, l.EnemyTag) {
		d.DamageTakenPercent += l.Percent
	}
}
