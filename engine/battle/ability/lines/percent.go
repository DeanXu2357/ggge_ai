package lines

import "github.com/DeanXu2357/ggge_ai/engine/battle/ability"

// The unconditional percent lines of the panel: "Increase ATK by 15%" and
// its kin. Each one adds to the percent of its stat in every strike, in the
// same sum as the conditional lines of that stat.

type MechAttackPercent struct{ Percent float64 }

func (l MechAttackPercent) Clone() ability.Line               { return l }
func (l MechAttackPercent) OnAttack(a *ability.AttackContext) { a.MechAttackPercent += l.Percent }

type MechDefensePercent struct{ Percent float64 }

func (l MechDefensePercent) Clone() ability.Line               { return l }
func (l MechDefensePercent) OnDefend(d *ability.DefendContext) { d.MechDefensePercent += l.Percent }

// The hit rate reads the mobility of both sides, so the line acts in the
// strike its holder fires and in the strike it takes.
type MechMobilityPercent struct{ Percent float64 }

func (l MechMobilityPercent) Clone() ability.Line               { return l }
func (l MechMobilityPercent) OnAttack(a *ability.AttackContext) { a.MechMobilityPercent += l.Percent }
func (l MechMobilityPercent) OnDefend(d *ability.DefendContext) { d.MechMobilityPercent += l.Percent }

type PilotRangedPercent struct{ Percent float64 }

func (l PilotRangedPercent) Clone() ability.Line               { return l }
func (l PilotRangedPercent) OnAttack(a *ability.AttackContext) { a.PilotRangedPercent += l.Percent }

type PilotMeleePercent struct{ Percent float64 }

func (l PilotMeleePercent) Clone() ability.Line               { return l }
func (l PilotMeleePercent) OnAttack(a *ability.AttackContext) { a.PilotMeleePercent += l.Percent }

type PilotAwakenPercent struct{ Percent float64 }

func (l PilotAwakenPercent) Clone() ability.Line               { return l }
func (l PilotAwakenPercent) OnAttack(a *ability.AttackContext) { a.PilotAwakenPercent += l.Percent }

type PilotDefensePercent struct{ Percent float64 }

func (l PilotDefensePercent) Clone() ability.Line               { return l }
func (l PilotDefensePercent) OnDefend(d *ability.DefendContext) { d.PilotDefensePercent += l.Percent }

type PilotReactionPercent struct{ Percent float64 }

func (l PilotReactionPercent) Clone() ability.Line               { return l }
func (l PilotReactionPercent) OnDefend(d *ability.DefendContext) { d.PilotReactionPercent += l.Percent }
