// Package lines holds the effect lines of the game the engine reads, one
// type for each line.
package lines

import (
	"slices"

	"github.com/DeanXu2357/ggge_ai/engine/battle/ability"
)

// MechAttackPercentAgainstTag is the attack half of an "Advantage" ability:
// against an enemy whose mech carries the tag, the mech attack rises by the
// percent.
type MechAttackPercentAgainstTag struct {
	EnemyTag int
	Percent  float64
}

func (l MechAttackPercentAgainstTag) Clone() ability.Line { return l }

func (l MechAttackPercentAgainstTag) OnAttack(a *ability.AttackContext) {
	if slices.Contains(a.Defender.Mech.Tags, l.EnemyTag) {
		a.MechAttackPercent += l.Percent
	}
}

// MechDefensePercentAgainstTag is the defense half of an "Advantage"
// ability: against an enemy whose mech carries the tag, the mech defense
// rises by the percent.
type MechDefensePercentAgainstTag struct {
	EnemyTag int
	Percent  float64
}

func (l MechDefensePercentAgainstTag) Clone() ability.Line { return l }

func (l MechDefensePercentAgainstTag) OnDefend(d *ability.DefendContext) {
	if slices.Contains(d.Attacker.Mech.Tags, l.EnemyTag) {
		d.MechDefensePercent += l.Percent
	}
}
