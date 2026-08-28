package board

import (
	"math"

	"github.com/DeanXu2357/ggge_ai/engine/battle"
)

// The frozen goldens under tests/fixtures/engine hold the values of the
// Python 'round', which rounds a half to the even integer, so the rounding
// is RoundToEven and not Round.
//
// The terrain correction is NoTerrainCorrection for every weapon. The
// correction is the effect of a weapon ability that reads the terrain of the
// cell of the target, and the engine models no ability yet. The function
// takes no terrain and no board on purpose: issue #80 gives the weapon its
// ability list, and the signature changes with it.
func StrikeDamage(attacker, defender *battle.Unit, weapon *battle.Weapon, defense float64) int {
	raw := ExpectedDamage(*weapon, attacker, defender, NoTerrainCorrection,
		debuffBonus(defender), 0, defense)
	return int(math.RoundToEven(raw))
}

func debuffBonus(defender *battle.Unit) float64 {
	var sum float64
	for _, debuff := range defender.Debuffs {
		sum += debuff.Magnitude
	}
	return sum
}

// The hit formula reads the accuracy from the weapon itself, so this
// function passes the dodge penalty alone.
func StrikeHitProbability(attacker, defender *battle.Unit, weapon *battle.Weapon,
	dodging bool) float64 {
	ability := 0.0
	if dodging {
		ability -= DodgeHitPenalty
	}
	return HitProbability(*weapon, attacker, defender, ability)
}

func (b *Board) counterWeapon(defender *battle.Unit, name string, attacker battle.Footprint) *battle.Weapon {
	distance := SpanDistance(defender.Footprint, attacker)
	for index := range defender.Mech.Weapons {
		weapon := &defender.Mech.Weapons[index]
		if name != "" && weapon.Name != name {
			continue
		}
		if counterFits(defender, weapon, distance) {
			return weapon
		}
	}
	return nil
}

func counterFits(defender *battle.Unit, weapon *battle.Weapon, distance int) bool {
	return !weapon.MapWeapon && weapon.CanCounter && defender.HasENFor(*weapon) &&
		weapon.Range.Holds(distance)
}
