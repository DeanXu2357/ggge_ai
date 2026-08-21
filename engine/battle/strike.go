package battle

import "math"

// StrikeDamage gives the hit points that one shot of the weapon takes off the
// defender. The oracle 'src/ggge_ai/sandbox/model.py' rounds with the Python
// 'round', which rounds a half to the even integer; the engine must give the
// same integer, so the rounding is RoundToEven and not Round.
func StrikeDamage(attacker, defender *Unit, weapon *Weapon, defense float64, rules Rules) int {
	raw := ExpectedDamage(weapon.Power, attacker, defender, rules.Terrain,
		debuffBonus(defender), 0, defense)
	return int(math.RoundToEven(raw))
}

// A debuff of the defender raises the damage it takes: the magnitudes go into
// the bonus term of the damage scale.
func debuffBonus(defender *Unit) float64 {
	var sum float64
	for _, debuff := range defender.Debuffs {
		sum += debuff.Magnitude
	}
	return sum
}

// The accuracy of the weapon is the base of the rate, and the hit formula
// reads it from the weapon. The dodge of the defender is a correction beside
// it, so this function passes the penalty alone and never the accuracy.
func StrikeHitProbability(attacker, defender *Unit, weapon *Weapon,
	dodging bool, rules Rules) float64 {
	ability := 0.0
	if dodging {
		ability -= rules.DodgeHitPenalty
	}
	return HitProbability(*weapon, attacker, defender, ability)
}

// StanceMultiplier gives the damage multiplier of the stance that the defender
// takes for itself. Dodge and counter carry no reduction.
func (r Rules) StanceMultiplier(stance Stance) float64 {
	switch stance {
	case StanceDefend:
		return r.DefendMultiplier
	case StanceShield:
		return r.ShieldMultiplier
	default:
		return NoDefenseMultiplier
	}
}

// InterceptionMultiplier gives the damage multiplier of a unit that takes a
// strike for another one. The interceptor takes it in a defense state, and a
// unit that carries a shield takes it in a shield state
// (docs/reference/combat-formulas.md, issue #20).
func (r Rules) InterceptionMultiplier(interceptor *Unit) float64 {
	base := r.SupportDefendMultiplier
	if interceptor.HasShield {
		base = r.ShieldMultiplier
	}
	return base * (1 - interceptor.InterceptionReduction)
}

// CounterWeapon gives the weapon that the defender fires back with against a
// strike from 'attacker', or nil. An empty name takes the first weapon that
// fits.
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
