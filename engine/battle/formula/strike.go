package formula

import (
	"math"
)

// The frozen goldens under tests/fixtures/engine hold the values of the
// Python 'round', which rounds a half to the even integer, so the rounding
// is RoundToEven and not Round.
func StrikeDamage(power float64, attacker, defender Side,
	terrain, bonuses, penalties, defense float64) int {
	raw := ExpectedDamage(power, attacker, defender, terrain, bonuses, penalties, defense)
	return int(math.RoundToEven(raw))
}

// correction is the sum of the ability lines of both sides in points of the
// hit rate: the accuracy of the attacker less the evasion of the defender.
func StrikeHitProbability(accuracy float64, attacker, defender Side, correction float64, dodging bool) float64 {
	if dodging {
		correction -= DodgeHitPenalty
	}
	return HitProbability(accuracy, attacker, defender, correction)
}
