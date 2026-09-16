package lines

import "github.com/DeanXu2357/ggge_ai/engine/battle/ability"

// The lines of the panel that change the hit rate, in points of the rate.
// "Psycho-Frame" is one row of each.

// AccuracyPercent: "Increase own ACC by 5%."
type AccuracyPercent struct{ Percent float64 }

func (l AccuracyPercent) Clone() ability.Line               { return l }
func (l AccuracyPercent) OnAttack(a *ability.AttackContext) { a.AccuracyPercent += l.Percent }

// EvasionPercent: "Increase Evasion by 5%."
type EvasionPercent struct{ Percent float64 }

func (l EvasionPercent) Clone() ability.Line               { return l }
func (l EvasionPercent) OnDefend(d *ability.DefendContext) { d.EvasionPercent += l.Percent }
