package formula

import (
	"math"
)

const (
	hitAttackerMobility = 0.00732
	hitDefenderMobility = 0.00662
	hitPilotDivisor     = 25.0
)

func HitRatePercent(accuracy float64, attacker, defender Side,
	abilityCorrection float64) float64 {
	rate := accuracy +
		hitAttackerMobility*attacker.Mobility -
		hitDefenderMobility*defender.Mobility +
		(attacker.PilotAttack-defender.PilotReaction)/hitPilotDivisor +
		abilityCorrection
	return math.Max(0, math.Min(100, rate))
}

func HitProbability(accuracy float64, attacker, defender Side,
	abilityCorrection float64) float64 {
	return HitRatePercent(accuracy, attacker, defender, abilityCorrection) / 100
}
