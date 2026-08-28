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

func StrikeHitProbability(accuracy float64, attacker, defender Side, dodging bool) float64 {
	ability := 0.0
	if dodging {
		ability -= DodgeHitPenalty
	}
	return HitProbability(accuracy, attacker, defender, ability)
}
