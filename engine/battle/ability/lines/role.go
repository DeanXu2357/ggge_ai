package lines

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/ability"
)

// The lines of the panel that hold on what the holder is in the exchange: a
// supporter fires or takes a strike for another unit.

// MechDefensePercentOnSupportDefense: "When executing Support Defense,
// increase own DEF by 20%."
type MechDefensePercentOnSupportDefense struct{ Percent float64 }

func (l MechDefensePercentOnSupportDefense) Clone() ability.Line { return l }
func (l MechDefensePercentOnSupportDefense) OnDefend(d *ability.DefendContext) {
	if d.Defender.Part == ability.PartSupport {
		d.MechDefensePercent += l.Percent
	}
}

// MechDefensePercentOnSupportDefenseWithMechType: "When piloting units with
// specified types, and executing Support Defense, increase own DEF by 20%."
// A pilot line that reads the type of the mech it rides.
type MechDefensePercentOnSupportDefenseWithMechType struct {
	MechType battle.MechType
	Percent  float64
}

func (l MechDefensePercentOnSupportDefenseWithMechType) Clone() ability.Line { return l }
func (l MechDefensePercentOnSupportDefenseWithMechType) OnDefend(d *ability.DefendContext) {
	if d.Defender.Part == ability.PartSupport && d.Defender.Mech.Type == l.MechType {
		d.MechDefensePercent += l.Percent
	}
}

// MechAttackPercentOnSupportWithMechType: "When piloting units with
// specified types and executing Support Attack/Counter, increase ATK by
// 25%." The datamine names both support roles on one line.
type MechAttackPercentOnSupportWithMechType struct {
	MechType battle.MechType
	Percent  float64
}

func (l MechAttackPercentOnSupportWithMechType) Clone() ability.Line { return l }
func (l MechAttackPercentOnSupportWithMechType) OnAttack(a *ability.AttackContext) {
	if a.Attacker.Part == ability.PartSupport && a.Attacker.Mech.Type == l.MechType {
		a.MechAttackPercent += l.Percent
	}
}
