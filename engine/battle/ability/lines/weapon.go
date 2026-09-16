package lines

import (
	"slices"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/ability"
)

// The lines of the panel that hold on the weapon fired at the holder.

// DamageTakenPercentAgainstWeaponAttribute: "When the enemy attacks with
// physical weapons, reduce damage taken by 30%" is the attribute physical
// with the percent -30.
type DamageTakenPercentAgainstWeaponAttribute struct {
	Attribute battle.WeaponAttribute
	Percent   float64
}

func (l DamageTakenPercentAgainstWeaponAttribute) Clone() ability.Line { return l }
func (l DamageTakenPercentAgainstWeaponAttribute) OnDefend(d *ability.DefendContext) {
	if slices.Contains(d.Weapon.Attributes, l.Attribute) {
		d.DamageTakenPercent += l.Percent
	}
}

// DamageTakenPercentAgainstWeaponAttributeAndCategory: "When the enemy
// attacks with beam ranged weapons, reduce damage taken by 50%" (I-Field,
// Fin Funnel Barrier) is the attribute beam with the category ranged. A
// weapon that carries the attribute among two meets the line; that the game
// reads it so is a hypothesis.
type DamageTakenPercentAgainstWeaponAttributeAndCategory struct {
	Attribute battle.WeaponAttribute
	Category  battle.WeaponCategory
	Percent   float64
}

func (l DamageTakenPercentAgainstWeaponAttributeAndCategory) Clone() ability.Line { return l }
func (l DamageTakenPercentAgainstWeaponAttributeAndCategory) OnDefend(d *ability.DefendContext) {
	if slices.Contains(d.Weapon.Attributes, l.Attribute) && slices.Contains(d.Weapon.Categories, l.Category) {
		d.DamageTakenPercent += l.Percent
	}
}
