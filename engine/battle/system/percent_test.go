package system

import (
	"testing"

	"github.com/stretchr/testify/assert"

	"github.com/DeanXu2357/ggge_ai/engine/battle/ability"
	"github.com/DeanXu2357/ggge_ai/engine/battle/ability/lines"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

// Every unconditional percent line of the panel gives the exchange of the
// unit whose stat is already scaled: the base times the percent, floored.
// A line of the actor changes what the actor fires or takes; the hit rate
// stands in for the damage where a stated hit hides the stat.
func TestAnUnconditionalPercentLineGivesTheExchangeOfTheScaledStat(t *testing.T) {
	mainDamage := func(t *testing.T, b state.Battle) float64 { return float64(resolveDuel(t, b).main) }
	counterDamage := func(t *testing.T, b state.Battle) float64 { return float64(resolveDuel(t, b).counter) }
	mainHitRate := func(t *testing.T, b state.Battle) float64 {
		actor, target := unitOf(b, actorID), unitOf(b, targetID)
		return duelExchange(b).strikeHitProbability(actor, target, &actor.Mech.Weapons[0], false)
	}
	counterHitRate := func(t *testing.T, b state.Battle) float64 {
		actor, target := unitOf(b, actorID), unitOf(b, targetID)
		return duelExchange(b).strikeHitProbability(target, actor, &target.Mech.Weapons[0], false)
	}
	for name, tc := range map[string]struct {
		line    ability.Line
		stated  func(u unit)
		measure func(t *testing.T, b state.Battle) float64
	}{
		"mech attack":    {lines.MechAttackPercent{Percent: 15}, func(u unit) { u.Mech.Attack = 4830 }, mainDamage},
		"mech defense":   {lines.MechDefensePercent{Percent: 15}, func(u unit) { u.Mech.Defense = 4485 }, counterDamage},
		"pilot ranged":   {lines.PilotRangedPercent{Percent: 15}, func(u unit) { u.Pilot.Ranged = 253 }, mainDamage},
		"pilot melee":    {lines.PilotMeleePercent{Percent: 15}, func(u unit) { u.Pilot.Melee = 253 }, mainDamage},
		"pilot awaken":   {lines.PilotAwakenPercent{Percent: 15}, func(u unit) { u.Pilot.Awaken = 253 }, mainDamage},
		"pilot defense":  {lines.PilotDefensePercent{Percent: 15}, func(u unit) { u.Pilot.Defense = 218 }, counterDamage},
		"pilot reaction": {lines.PilotReactionPercent{Percent: 15}, func(u unit) { u.Pilot.Reaction = 235 }, counterHitRate},
		"mech mobility":  {lines.MechMobilityPercent{Percent: 15}, func(u unit) { u.Mech.Mobility = 356 }, mainHitRate},
	} {
		t.Run(name, func(t *testing.T) {
			plain := tc.measure(t, scenarioDuel())

			lined := scenarioDuel()
			lined.Values.Units[actorID].SetAbilities([]ability.Line{tc.line}, nil)
			withLine := tc.measure(t, lined)

			stated := scenarioDuel()
			tc.stated(unitOf(stated, actorID))
			withStat := tc.measure(t, stated)

			assert.Equal(t, withStat, withLine, "the line gives the value of the stated stat")
			assert.NotEqual(t, plain, withLine, "the line changes the value")
		})
	}
}

// The mobility of the defender lowers the hit rate of the strike it takes,
// so the same line acts on both sides.
func TestAMobilityLineOfTheDefenderLowersTheHitRateOfTheStrikeItTakes(t *testing.T) {
	hitRate := func(b state.Battle) float64 {
		actor, target := unitOf(b, actorID), unitOf(b, targetID)
		return duelExchange(b).strikeHitProbability(actor, target, &actor.Mech.Weapons[0], false)
	}
	lined := scenarioDuel()
	lined.Values.Units[targetID].SetAbilities([]ability.Line{lines.MechMobilityPercent{Percent: 15}}, nil)
	stated := scenarioDuel()
	stated.Content.Units[targetID].Mech.Mobility = 356

	assert.Equal(t, hitRate(stated), hitRate(lined))
	assert.Less(t, hitRate(lined), hitRate(scenarioDuel()))
}

// Two lines on one stat add before the one multiplication: 4200 with +15%
// and +12% is floor(4200 × 1.27) = 5334, not floor(floor(4200 × 1.15) × 1.12).
func TestTwoPercentLinesOnOneStatAddBeforeTheMultiplication(t *testing.T) {
	lined := scenarioDuel()
	lined.Values.Units[actorID].SetAbilities([]ability.Line{
		lines.MechAttackPercent{Percent: 15}, lines.MechAttackPercent{Percent: 12}}, nil)
	stated := scenarioDuel()
	stated.Content.Units[actorID].Mech.Attack = 5334

	assert.Equal(t, resolveDuel(t, stated).main, resolveDuel(t, lined).main)
}

// A conditional line joins the sum of the unconditional lines of its stat:
// the datamine gives both the trait type 7, so ATK +15% and "Advantage" +15%
// against a tagged enemy give floor(4200 × 1.30) = 5460, and not 4830 × 1.15.
func TestAConditionalLineJoinsTheSumOfItsStat(t *testing.T) {
	lined := scenarioDuel()
	lined.Content.Units[targetID].Mech.Tags = []int{zeonTagID}
	lined.Values.Units[actorID].SetAbilities([]ability.Line{
		lines.MechAttackPercent{Percent: 15},
		lines.MechAttackPercentAgainstTag{EnemyTag: zeonTagID, Percent: 15}}, nil)
	stated := scenarioDuel()
	stated.Content.Units[targetID].Mech.Tags = []int{zeonTagID}
	stated.Content.Units[actorID].Mech.Attack = 5460

	assert.Equal(t, resolveDuel(t, stated).main, resolveDuel(t, lined).main)
}
