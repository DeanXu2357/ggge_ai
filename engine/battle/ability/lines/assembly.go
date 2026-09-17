package lines

import "github.com/DeanXu2357/ggge_ai/engine/battle/ability"

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
