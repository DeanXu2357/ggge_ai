package board

import (
	"math"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

const (
	hitAttackerMobility = 0.00732
	hitDefenderMobility = 0.00662
	hitPilotDivisor     = 25.0
)

func HitRatePercent(weapon battle.Weapon, attacker, defender *battle.Unit, abilityCorrection float64) float64 {
	rate := weapon.Accuracy +
		hitAttackerMobility*attacker.Mech.Mobility -
		hitDefenderMobility*defender.Mech.Mobility +
		(attacker.Pilot.AttackFor(weapon)-defender.Pilot.Reaction)/hitPilotDivisor +
		abilityCorrection
	return math.Max(0, math.Min(100, rate))
}

func HitProbability(weapon battle.Weapon, attacker, defender *battle.Unit, abilityCorrection float64) float64 {
	return HitRatePercent(weapon, attacker, defender, abilityCorrection) / 100
}
