package system

import (
	"testing"

	"github.com/stretchr/testify/assert"

	"github.com/DeanXu2357/ggge_ai/engine/battle/ability"
	"github.com/DeanXu2357/ggge_ai/engine/battle/ability/lines"
	"github.com/DeanXu2357/ggge_ai/engine/battle/state"
)

// mainHitRate answers the hit rate of the main strike of the duel, with the
// accuracy of the actor's weapon moved by the offset.
func mainHitRate(b state.Battle, accuracyOffset float64) float64 {
	b.Content.Units[actorID].Mech.Weapons[0].Accuracy += accuracyOffset
	actor, target := unitOf(b, actorID), unitOf(b, targetID)
	return strikeHitProbability(actor, target, &actor.Mech.Weapons[0], false)
}

// A hit line adds points to the hit rate, the way the accuracy of the
// weapon does: accuracy +5 of the attacker is a weapon 5 more accurate,
// evasion +5 of the defender a weapon 5 less accurate, and the two cancel.
func TestAHitLineAddsPointsToTheHitRate(t *testing.T) {
	accurate := scenarioDuel()
	accurate.Values.Units[actorID].SetAbilities([]ability.Line{lines.AccuracyPercent{Percent: 5}})
	evasive := scenarioDuel()
	evasive.Values.Units[targetID].SetAbilities([]ability.Line{lines.EvasionPercent{Percent: 5}})
	both := scenarioDuel()
	both.Values.Units[actorID].SetAbilities([]ability.Line{lines.AccuracyPercent{Percent: 5}})
	both.Values.Units[targetID].SetAbilities([]ability.Line{lines.EvasionPercent{Percent: 5}})

	assert.InDelta(t, mainHitRate(scenarioDuel(), 5), mainHitRate(accurate, 0), 1e-12, "accuracy +5")
	assert.InDelta(t, mainHitRate(scenarioDuel(), -5), mainHitRate(evasive, 0), 1e-12, "evasion +5")
	assert.InDelta(t, mainHitRate(scenarioDuel(), 0), mainHitRate(both, 0), 1e-12, "the two cancel")
	assert.Greater(t, mainHitRate(accurate, 0), mainHitRate(scenarioDuel(), 0))
}
