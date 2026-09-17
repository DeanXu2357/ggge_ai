package lines

import (
	"github.com/DeanXu2357/ggge_ai/engine/battle/ability"
	"github.com/DeanXu2357/ggge_ai/engine/battle/def"
)

// The lines of the panel that change what a weapon costs to fire.

// WeaponENCostPercentOnSupportWithMechType: "When piloting units with
// specified types and executing Support Attack/Counter, reduce own weapon
// EN consumption by 20%." A pilot line that reads the type of the mech it
// rides; the percent is signed, so the line of the game carries -20.
type WeaponENCostPercentOnSupportWithMechType struct {
	MechType def.MechType
	Percent  float64
}

func (l WeaponENCostPercentOnSupportWithMechType) Clone() ability.Line { return l }
func (l WeaponENCostPercentOnSupportWithMechType) OnWeaponCost(w *ability.WeaponCostContext) {
	if w.Shooter.Part == ability.PartSupport && w.Shooter.Mech.Type == l.MechType {
		w.ENCostPercent += l.Percent
	}
}
