package battle

import "math"

// The frozen goldens under tests/fixtures/engine hold the values of the
// Python 'round', which rounds a half to the even integer, so the rounding
// is RoundToEven and not Round.
func StrikeDamage(attacker, defender *Unit, weapon *Weapon, defense float64, rules Rules) int {
	raw := ExpectedDamage(weapon.Power, attacker, defender, rules.Terrain,
		debuffBonus(defender), 0, defense)
	return int(math.RoundToEven(raw))
}

func debuffBonus(defender *Unit) float64 {
	var sum float64
	for _, debuff := range defender.Debuffs {
		sum += debuff.Magnitude
	}
	return sum
}

// The hit formula reads the accuracy from the weapon itself, so this
// function passes the dodge penalty alone.
func StrikeHitProbability(attacker, defender *Unit, weapon *Weapon,
	dodging bool, rules Rules) float64 {
	ability := 0.0
	if dodging {
		ability -= rules.DodgeHitPenalty
	}
	return HitProbability(*weapon, attacker, defender, ability)
}

// The reaction menu offers no shield stance, so a defender that carries a
// shield defends with the shield here, in the damage (issue #63).
func (r Rules) StanceMultiplier(stance Stance, defender *Unit) float64 {
	if stance != StanceDefend {
		return NoDefenseMultiplier
	}
	if defender.HasShield {
		return r.ShieldMultiplier
	}
	return r.DefendMultiplier
}

func (r Rules) InterceptionMultiplier(interceptor *Unit) float64 {
	base := r.SupportDefendMultiplier
	if interceptor.HasShield {
		base = r.ShieldMultiplier
	}
	return base * (1 - interceptor.InterceptionReduction)
}

func (b *Board) CounterWeapon(defender *Unit, name string, attacker Footprint) *Weapon {
	distance := SpanDistance(defender.Footprint, attacker)
	for index := range defender.Weapons {
		weapon := &defender.Weapons[index]
		if name != "" && weapon.Name != name {
			continue
		}
		if counterFits(defender, weapon, distance) {
			return weapon
		}
	}
	return nil
}

func counterFits(defender *Unit, weapon *Weapon, distance int) bool {
	return !weapon.MapWeapon && weapon.CanCounter && defender.HasENFor(*weapon) &&
		weapon.Range.Holds(distance)
}
