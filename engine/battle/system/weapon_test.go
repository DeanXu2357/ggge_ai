package system

import (
	"testing"

	"github.com/stretchr/testify/assert"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/ability"
	"github.com/DeanXu2357/ggge_ai/engine/battle/ability/lines"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

// The duel with the weapon of the actor given the attributes and the
// categories of the case.
func duelWithActorWeapon(attributes []battle.WeaponAttribute, categories []battle.WeaponCategory) state.Battle {
	b := scenarioDuel()
	weapon := &b.Content.Units[actorID].Mech.Weapons[0]
	weapon.Attributes, weapon.Categories = attributes, categories
	return b
}

// A damage-taken line joins the sum of ⑨ with the debuffs, so the line on
// the target gives the main strike of a target that carries a debuff of the
// same magnitude; a weapon the line does not name meets no line.
func TestADamageTakenLineOfTheWeaponJoinsTheSumOfTheDamageScale(t *testing.T) {
	beam, physical := []battle.WeaponAttribute{battle.WeaponAttributeBeam}, []battle.WeaponAttribute{battle.WeaponAttributePhysical}
	ranged, melee := []battle.WeaponCategory{battle.WeaponCategoryRanged}, []battle.WeaponCategory{battle.WeaponCategoryMelee}
	iField := lines.DamageTakenPercentAgainstWeaponAttributeAndCategory{
		Attribute: battle.WeaponAttributeBeam, Category: battle.WeaponCategoryRanged, Percent: -50}
	physicalReduced := lines.DamageTakenPercentAgainstWeaponAttribute{Attribute: battle.WeaponAttributePhysical, Percent: -30}

	for name, tc := range map[string]struct {
		line       ability.Line
		attributes []battle.WeaponAttribute
		categories []battle.WeaponCategory
		magnitude  float64 // the debuff that gives the same ⑨; 0 is no effect
	}{
		"I-Field against a beam ranged weapon":       {iField, beam, ranged, -0.5},
		"I-Field against a beam melee weapon":        {iField, beam, melee, 0},
		"I-Field against a physical ranged weapon":   {iField, physical, ranged, 0},
		"I-Field against a beam and physical weapon": {iField, append(beam, physical...), ranged, -0.5},
		"physical reduced against a physical weapon": {physicalReduced, physical, melee, -0.3},
		"physical reduced against a beam weapon":     {physicalReduced, beam, ranged, 0},
	} {
		t.Run(name, func(t *testing.T) {
			lined := duelWithActorWeapon(tc.attributes, tc.categories)
			lined.Values.Units[targetID].SetAbilities([]ability.Line{tc.line})

			debuffed := duelWithActorWeapon(tc.attributes, tc.categories)
			if tc.magnitude != 0 {
				debuffed.Values.Units[targetID].Debuffs = []battle.Debuff{{Kind: "same", Magnitude: tc.magnitude}}
			}

			assert.Equal(t, resolveDuel(t, debuffed).main, resolveDuel(t, lined).main)
		})
	}
}
