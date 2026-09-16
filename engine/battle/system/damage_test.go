package system

import (
	"testing"

	"github.com/stretchr/testify/assert"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
	"github.com/DeanXu2357/ggge_ai/engine/battle/ability"
	"github.com/DeanXu2357/ggge_ai/engine/battle/ability/lines"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

const efsfTagID = 1014

// mainDamageWithDebuff answers the main strike of the duel when the target
// carries a debuff of the magnitude, which is the ⑨ a line of that share
// must reproduce; a magnitude of 0 is the plain duel.
func mainDamageWithDebuff(t *testing.T, tags func(b state.Battle), magnitude float64) int {
	t.Helper()
	b := scenarioDuel()
	tags(b)
	if magnitude != 0 {
		b.Values.Units[targetID].Debuffs = []battle.Debuff{{Kind: "same", Magnitude: magnitude}}
	}
	return resolveDuel(t, b).main
}

// A damage line joins the sum of ⑨ with the debuffs of the defender, from
// either side of the strike, and a condition on a tag reads the unit the
// line names: the mech of the holder, or the mech of the enemy.
func TestADamageLineJoinsTheSumOfTheDamageScaleFromEitherSide(t *testing.T) {
	noTags := func(state.Battle) {}
	actorTagged := func(b state.Battle) { b.Content.Units[actorID].Mech.Tags = []int{efsfTagID} }
	targetTagged := func(b state.Battle) { b.Content.Units[targetID].Mech.Tags = []int{efsfTagID} }

	for name, tc := range map[string]struct {
		holder    int
		line      ability.Line
		tags      func(b state.Battle)
		magnitude float64
	}{
		"dealt +15 on the actor":                                {actorID, lines.DamageDealtPercent{Percent: 15}, noTags, 0.15},
		"dealt +15 on the mech tag, the actor rides the tag":    {actorID, lines.DamageDealtPercentOnMechTag{MechTag: efsfTagID, Percent: 15}, actorTagged, 0.15},
		"dealt +15 on the mech tag, the actor rides no tag":     {actorID, lines.DamageDealtPercentOnMechTag{MechTag: efsfTagID, Percent: 15}, targetTagged, 0},
		"taken -15 on the mech tag, the target rides the tag":   {targetID, lines.DamageTakenPercentOnMechTag{MechTag: efsfTagID, Percent: -15}, targetTagged, -0.15},
		"taken -15 on the mech tag, the target rides no tag":    {targetID, lines.DamageTakenPercentOnMechTag{MechTag: efsfTagID, Percent: -15}, actorTagged, 0},
		"dealt +10 against the tag, the target carries the tag": {actorID, lines.DamageDealtPercentAgainstTag{EnemyTag: efsfTagID, Percent: 10}, targetTagged, 0.10},
		"dealt +10 against the tag, the actor carries the tag":  {actorID, lines.DamageDealtPercentAgainstTag{EnemyTag: efsfTagID, Percent: 10}, actorTagged, 0},
		"taken -10 against the tag, the actor carries the tag":  {targetID, lines.DamageTakenPercentAgainstTag{EnemyTag: efsfTagID, Percent: -10}, actorTagged, -0.10},
		"taken -10 against the tag, the target carries the tag": {targetID, lines.DamageTakenPercentAgainstTag{EnemyTag: efsfTagID, Percent: -10}, targetTagged, 0},
	} {
		t.Run(name, func(t *testing.T) {
			lined := scenarioDuel()
			tc.tags(lined)
			lined.Values.Units[tc.holder].SetAbilities([]ability.Line{tc.line})

			assert.Equal(t, mainDamageWithDebuff(t, tc.tags, tc.magnitude), resolveDuel(t, lined).main)
		})
	}
}

// ⑨ is one sum: damage dealt +15% of the attacker and damage taken -15% of
// the defender cancel, and the strike is the plain strike. Two
// multiplications would give 1.15 × 0.85 = 0.9775 of it.
func TestDamageDealtAndDamageTakenAddIntoOneSum(t *testing.T) {
	lined := scenarioDuel()
	lined.Values.Units[actorID].SetAbilities([]ability.Line{lines.DamageDealtPercent{Percent: 15}})
	lined.Values.Units[targetID].SetAbilities([]ability.Line{lines.DamageTakenPercentOnMechTag{MechTag: efsfTagID, Percent: -15}})
	lined.Content.Units[targetID].Mech.Tags = []int{efsfTagID}

	assert.Equal(t, resolveDuel(t, scenarioDuel()).main, resolveDuel(t, lined).main)
}
