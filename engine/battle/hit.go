package battle

import "math"

const (
	hitBase             = 96.45
	hitAttackerMobility = 0.00732
	hitDefenderMobility = 0.00662
	hitPilotDivisor     = 25.0
)

func HitRatePercent(attacker, defender *Unit, abilityCorrection float64) float64 {
	rate := hitBase +
		hitAttackerMobility*attacker.Mobility -
		hitDefenderMobility*defender.Mobility +
		(attacker.PilotAttack-defender.Reaction)/hitPilotDivisor +
		abilityCorrection
	return math.Max(0, math.Min(100, rate))
}

func HitProbability(attacker, defender *Unit, abilityCorrection float64) float64 {
	return HitRatePercent(attacker, defender, abilityCorrection) / 100
}
