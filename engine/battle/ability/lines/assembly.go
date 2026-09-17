package lines

import (
	"slices"

	"github.com/DeanXu2357/ggge_ai/engine/battle/ability"
)

// The lines of the panel that change an allowance of the unit when it
// enters the battle: how many times it may support attack, support defend
// or act again after a kill.

// SupportAttackPlus: "Support Attack/Counter +1 time(s)."
type SupportAttackPlus struct{ Plus int }

func (l SupportAttackPlus) Clone() ability.Line                   { return l }
func (l SupportAttackPlus) OnAssemble(a *ability.AssembleContext) { a.SupportAttackPlus += l.Plus }

// SupportDefendPlus: "Support Defense +1 time(s)."
type SupportDefendPlus struct{ Plus int }

func (l SupportDefendPlus) Clone() ability.Line                   { return l }
func (l SupportDefendPlus) OnAssemble(a *ability.AssembleContext) { a.SupportDefendPlus += l.Plus }

// ChanceStepPlus: "Chance Step +1 time."
type ChanceStepPlus struct{ Plus int }

func (l ChanceStepPlus) Clone() ability.Line                   { return l }
func (l ChanceStepPlus) OnAssemble(a *ability.AssembleContext) { a.ChanceStepPlus += l.Plus }

// MaxHPPercent: "Increase Max HP by 15%." The percents of every line on
// the maximum add, and the assembly multiplies the base of the mech one
// time.
type MaxHPPercent struct{ Percent float64 }

func (l MaxHPPercent) Clone() ability.Line                   { return l }
func (l MaxHPPercent) OnAssemble(a *ability.AssembleContext) { a.MaxHPPercent += l.Percent }

// MaxENPercent: "Increase Max EN by 15%."
type MaxENPercent struct{ Percent float64 }

func (l MaxENPercent) Clone() ability.Line                   { return l }
func (l MaxENPercent) OnAssemble(a *ability.AssembleContext) { a.MaxENPercent += l.Percent }

// MoveRangePlusOnPilotTag: "When the piloting character has a specified
// tag, increase own MOV by 1." A mech line that reads the tags of the
// pilot who rides it.
type MoveRangePlusOnPilotTag struct {
	PilotTag int
	Plus     int
}

func (l MoveRangePlusOnPilotTag) Clone() ability.Line { return l }
func (l MoveRangePlusOnPilotTag) OnAssemble(a *ability.AssembleContext) {
	if slices.Contains(a.Unit.Pilot.Tags, l.PilotTag) {
		a.MoveRangePlus += l.Plus
	}
}
